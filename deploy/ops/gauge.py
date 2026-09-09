#!/usr/bin/env python3
"""gauge — reads the subscription seat's meters. Operator-side, root-only.

The seat that runs the agents' sessions is metered: a rolling five-hour
window, a weekly pool across every model, and the deepest tier on its
own weekly meter. None of it is ever a word to an agent; the seat
governor (seat_governor.py) reads these meters and shapes launches from
outside the agents' world.

Two credential classes exist and only one of them can read the meters:
  * the setup-token that runs sessions carries the inference scope only —
    the usage endpoint refuses it;
  * a browser-login credential — the CLI's own credentials file from an
    interactive login: an access token, a refresh token, and the
    user:profile scope. This module reads that one.

The login credential sustains itself. The access token expires within
hours, so a stale one is refreshed through the OAuth token endpoint and
the rotated pair is written back. After the first refresh the file on
the box IS the credential: the copy it was bootstrapped from now carries
a refresh token that rotation has invalidated, so a parameter store copy
is bootstrap-only and is never pulled over a live file. A box that stays
dark for weeks outlives its refresh token; the cure is one new login.

Reading the meters spends nothing on the seat. A token refresh opens a
window on it, at zero — expect that once after each bootstrap.

Both endpoints are unofficial. Re-verify them on every CLI re-pin.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
TOKEN_URL = "https://api.anthropic.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"   # the CLI's public client id
USER_AGENT = "alpaca-mind-gauge/1.0"
HTTP_TIMEOUT_S = 30

DEFAULT_PATH = "/var/lib/alpaca-mind/ops/gauge-credentials.json"


class GaugeError(RuntimeError):
    """The meters could not be read. The message never carries a token."""


# -- the credential file ------------------------------------------------------

def load(path: str | os.PathLike) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(d, dict) or not isinstance(d.get("claudeAiOauth"), dict):
        raise GaugeError("credential file is not a login credential")
    return d


def save(d: dict, path: str | os.PathLike) -> None:
    """Owner-only from the first byte: created 0600, then renamed into
    place so a reader never sees a half-written credential."""
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, indent=2))
    os.replace(tmp, p)


def bootstrap(path: str | os.PathLike, ssm_name: str,
              region: str | None = None) -> bool:
    """Seed the box file from the parameter store when — and only when —
    the file is absent. True when a credential is on disk afterwards."""
    p = Path(path)
    if p.exists():
        return True
    cmd = ["aws", "ssm", "get-parameter", "--name", ssm_name,
           "--with-decryption", "--query", "Parameter.Value",
           "--output", "text"]
    env = dict(os.environ)
    if region:
        env["AWS_DEFAULT_REGION"] = region
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                           env=env)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0:
        return False
    try:
        d = json.loads(r.stdout.strip())
    except ValueError:
        return False
    if not isinstance(d, dict) or not isinstance(d.get("claudeAiOauth"), dict):
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    save(d, p)
    return True


# -- the two endpoints ---------------------------------------------------------

def refresh(d: dict, path: str | os.PathLike) -> dict:
    c = d["claudeAiOauth"]
    if not c.get("refreshToken"):
        raise GaugeError("credential has no refresh token; a new login is needed")
    body = json.dumps({"grant_type": "refresh_token",
                       "refresh_token": c["refreshToken"],
                       "client_id": CLIENT_ID}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={
        "Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
            j = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 4xx here means the refresh token itself is dead — only a new
        # login cures that; the body is never surfaced (it is not ours).
        raise GaugeError(f"token refresh HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise GaugeError(f"token refresh failed: {type(e).__name__}") from None
    if not j.get("access_token"):
        raise GaugeError("token refresh returned no access token")
    c["accessToken"] = j["access_token"]
    if j.get("refresh_token"):
        c["refreshToken"] = j["refresh_token"]
    if j.get("expires_in"):
        c["expiresAt"] = int(time.time() * 1000) + int(j["expires_in"]) * 1000
    save(d, path)
    return d


def usage(token: str) -> dict:
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": "Bearer " + token,
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
        j = json.loads(r.read().decode("utf-8"))
    if not isinstance(j, dict):
        raise GaugeError("usage endpoint returned a non-object payload")
    return j


def raw(path: str | os.PathLike = DEFAULT_PATH) -> dict:
    """The seat's full usage payload, refreshing the credential once if
    the access token has gone stale (by its own clock, or by a 401)."""
    d = load(path)
    c = d["claudeAiOauth"]
    if not c.get("accessToken"):
        raise GaugeError("credential file has no access token")
    if int(c.get("expiresAt") or 0) <= int(time.time() * 1000):
        d = refresh(d, path)
        c = d["claudeAiOauth"]
    try:
        return usage(c["accessToken"])
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise GaugeError(f"usage endpoint HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise GaugeError(f"usage endpoint failed: {type(e).__name__}") from None
    d = refresh(d, path)
    try:
        return usage(d["claudeAiOauth"]["accessToken"])
    except urllib.error.HTTPError as e:
        raise GaugeError(f"usage endpoint HTTP {e.code} after refresh") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise GaugeError(f"usage endpoint failed: {type(e).__name__}") from None


# -- the meters ----------------------------------------------------------------

def _pct(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def to_epoch(iso: str | None) -> float | None:
    """An ISO-8601 instant (the payload's resets_at) as a unix time; None
    for anything unparseable — a missing reset time is never guessed."""
    if not iso or not isinstance(iso, str):
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def parse_meters(payload: dict) -> dict:
    """Percentages and reset instants from the usage payload. Every field
    is None when the payload lacks it — a consumer treats None as "not
    readable", never as zero.

      five_hour / five_hour_resets_at     the rolling session window
      weekly_all / weekly_resets_at       the weekly pool, all models
      weekly_fable / fable_resets_at      the deepest tier's own weekly
                                          meter (the scoped weekly limit)
      weekly_opus / opus_resets_at        a per-model weekly meter, when
                                          the payload carries one
    """
    five = payload.get("five_hour") if isinstance(payload.get("five_hour"), dict) else {}
    week = payload.get("seven_day") if isinstance(payload.get("seven_day"), dict) else {}
    opus = payload.get("seven_day_opus") if isinstance(payload.get("seven_day_opus"), dict) else {}
    out = {
        "five_hour": _pct(five.get("utilization")),
        "five_hour_resets_at": five.get("resets_at"),
        "weekly_all": _pct(week.get("utilization")),
        "weekly_resets_at": week.get("resets_at"),
        "weekly_fable": None,
        "fable_resets_at": None,
        "weekly_opus": _pct(opus.get("utilization")),
        "opus_resets_at": opus.get("resets_at"),
    }
    for lim in payload.get("limits") or []:
        if not isinstance(lim, dict):
            continue
        kind = lim.get("kind")
        if kind == "weekly_scoped":
            out["weekly_fable"] = _pct(lim.get("percent"))
            out["fable_resets_at"] = lim.get("resets_at")
        elif kind == "session" and out["five_hour"] is None:
            out["five_hour"] = _pct(lim.get("percent"))
            out["five_hour_resets_at"] = lim.get("resets_at")
        elif kind == "weekly_all" and out["weekly_all"] is None:
            out["weekly_all"] = _pct(lim.get("percent"))
            out["weekly_resets_at"] = lim.get("resets_at")
    out["read_at"] = time.time()
    return out


def meters(path: str | os.PathLike = DEFAULT_PATH) -> dict:
    return parse_meters(raw(path))


def main() -> int:
    ap = argparse.ArgumentParser(description="print the seat's meters")
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--raw", action="store_true",
                    help="print the whole usage payload instead")
    args = ap.parse_args()
    try:
        out = raw(args.path) if args.raw else meters(args.path)
    except (GaugeError, OSError, ValueError) as e:
        print(f"gauge: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
