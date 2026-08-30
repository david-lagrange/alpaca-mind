#!/usr/bin/env python3
"""sentinel — the agent's senses while it sleeps. No LLM, no cost.

Continuously:
  * evaluates agent-authored tripwires in state/triggers.json
  * adopts fills that land after the placing session ended (including
    multi-leg options orders) — the venue is the source of truth and
    nothing else closes that loop
  * runs the agent's own scanner scripts (see scanners.py)
  * snapshots the account balance for the equity curve
  * records a heartbeat event if the system goes quiet

When a trigger fires it writes state/wake_request.json; the supervisor
launches a session whose prompt opens with the trigger context. The
agent goes to sleep knowing its tripwires are armed.

triggers.json (agent-written at session close):
{
  "triggers": [
    {"id": "breakdown", "type": "price_below", "symbol": "SPY",
     "value": 500, "note": "invalidates thesis", "protective": true,
     "model": "fable", "effort": "xhigh",
     "charter": "prompts/CRISIS.md"},   # optional wake-as fields: the
                                        # wake runs as the mind, effort,
                                        # run_type, and charter the
                                        # trigger names
    {"id": "iv-pop", "type": "pct_move", "symbol": "QQQ",
     "value": 2.5, "window_min": 15},
    {"id": "fill", "type": "order_fill", "order_id": "abc-123"}
  ],
  "expire": "..."   # optional; protective triggers are typically
}                   # armed without a bound

Option symbols (OCC format) are watched through the options quote feed;
stock symbols through the stock feed — one triggers file covers both.

Run: sentinel.py --config /path/to/config.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import yaml

ENGINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE_DIR))

from ledger import Ledger, OPEN_ORDER_STATUSES as _OPEN_STATUSES  # noqa: E402
from venue import Venue            # noqa: E402

OCC_RE = re.compile(r"^[A-Z.]{1,6}\d{6}[CP]\d{8}$")


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}",
          flush=True)


class Sentinel:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.state = Path(cfg["paths"]["state"])
        self.state.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(cfg["paths"]["ledger"])
        self.venue = Venue()
        # rolling price history per symbol: deque[(ts, price)]
        self.prices: dict[str, deque] = defaultdict(lambda: deque(maxlen=4096))
        # freshest full quote per symbol — bid/ask-aware trigger types
        # read this; LAST alone false-fires in thin books
        self.latest_quotes: dict[str, dict] = {}
        self.day_range: dict[str, dict] = {}
        self.fired: dict[str, float] = {}
        self.last_balance = 0.0
        # heartbeat debounce persists across restarts so a service
        # restart cannot re-fire an alarm that already sounded
        try:
            self.last_heartbeat_alarm = float(
                (self.state / ".heartbeat_alarm_ts").read_text())
        except (OSError, ValueError):
            self.last_heartbeat_alarm = 0.0
        self.no_data_polls: dict[str, int] = {}
        self.warned_dead: set[str] = set()
        self.warned_windows: set[str] = set()
        self.warned_bad_triggers: set[str] = set()
        # agent-authored autonomous scanners: isolated subprocesses on
        # their own cadence; shadow mode, wake budgets, and quarantine
        # live in scanners.py. Config-gated.
        self.scanners = None
        if (cfg.get("scanners") or {}).get("enabled", True):
            from scanners import ScannerRunner
            self.scanners = ScannerRunner(cfg, self.ledger,
                                          self.request_wake, log)

    # -- state files -----------------------------------------------------

    def load_triggers(self) -> list[dict]:
        f = self.state / "triggers.json"
        if not f.exists():
            return []
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError:
            return []
        expire = data.get("expire")
        if expire:
            try:
                exp_ts = datetime.fromisoformat(
                    str(expire).replace("Z", "+00:00")).timestamp()
                if time.time() > exp_ts:
                    return []
            except ValueError:
                pass
        return data.get("triggers", [])

    def request_wake(self, reason: str, context: dict,
                     protective: bool = False,
                     wake_as: dict | None = None) -> None:
        """Debounced: at most one pending wake request at a time.
        wake_as (run_type/model/effort/charter) carries the agent's own
        choice of mind and frame for the wake — a sensor the agent armed
        has the same choice rights as a slot the agent scheduled."""
        f = self.state / "wake_request.json"
        if f.exists():
            return
        body = {
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason, "context": context, "protective": protective,
        }
        if wake_as:
            body["wake_as"] = {k: wake_as[k] for k in
                               ("run_type", "model", "effort", "charter")
                               if wake_as.get(k)}
        f.write_text(json.dumps(body, indent=2, default=str))
        self.ledger.record_event("sentinel", "wake_requested",
                                 {"reason": reason, **context})
        log(f"WAKE requested: {reason}")

    # -- data collection -------------------------------------------------

    def watched_symbols(self, triggers: list[dict]) -> list[str]:
        syms = {t["symbol"] for t in triggers
                if isinstance(t, dict) and t.get("symbol")}
        for t in self.ledger.open_trades():
            syms.add(t["symbol"])
        return sorted(syms)

    def poll_quotes(self, symbols: list[str]) -> dict[str, float]:
        if not symbols:
            return {}
        now = time.time()
        latest: dict[str, float] = {}
        stocks = [s for s in symbols if not OCC_RE.match(s)]
        options = [s for s in symbols if OCC_RE.match(s)]
        quotes: list[dict] = []
        try:
            if stocks:
                quotes += self.venue.quotes(stocks)
            if options:
                quotes += [q | {"last": None}
                           for q in self.venue.option_quotes(options)]
        except Exception as e:
            log(f"quote poll error: {e!r}")
            return latest
        for q in quotes:
            sym = q.get("symbol")
            if not sym:
                continue
            # keep the full quote BEFORE the price gate: an empty-book
            # market can have bid/ask but no last (or vice versa), and
            # the bid/ask trigger types still need what we do have
            self.latest_quotes[sym] = q
            bid, ask = q.get("bid") or 0, q.get("ask") or 0
            px = q.get("last") or ((bid + ask) / 2 if bid and ask
                                   else bid or None)
            if not px:
                continue
            latest[sym] = px
            self.prices[sym].append((now, px))
            day = time.strftime("%Y-%m-%d")
            r = self.day_range.setdefault(sym, {"hi": px, "lo": px,
                                                "day": day})
            if r["day"] != day:
                r.update({"hi": px, "lo": px, "day": day})
            r["hi"] = max(r["hi"], px)
            r["lo"] = min(r["lo"], px)
        return latest

    def price_pct_move(self, symbol: str, window_min: float) -> float | None:
        hist = self.prices.get(symbol)
        if not hist or len(hist) < 2:
            return None
        cutoff = time.time() - window_min * 60
        past = [p for ts, p in hist if ts <= cutoff]
        ref = past[-1] if past else hist[0][1]
        cur = hist[-1][1]
        return (cur - ref) / ref * 100 if ref else None

    # -- trigger evaluation ----------------------------------------------

    def evaluate(self, triggers: list[dict], latest: dict[str, float]) -> None:
        # A trigger on a symbol that never produces quote data is
        # silently inert — surface that loudly instead of letting a
        # tripwire be a dud.
        for sym in {t["symbol"] for t in triggers
                    if isinstance(t, dict) and t.get("symbol")}:
            if sym in latest or sym in self.prices:
                self.no_data_polls.pop(sym, None)
                continue
            self.no_data_polls[sym] = self.no_data_polls.get(sym, 0) + 1
            if self.no_data_polls[sym] >= 30 and sym not in self.warned_dead:
                self.warned_dead.add(sym)
                log(f"WARNING: trigger symbol {sym} returns no quote data "
                    "— its tripwires are inert")
                self.ledger.record_event("sentinel",
                                         "trigger_symbol_no_data",
                                         {"symbol": sym})

        debounce = self.cfg["sessions"]["min_wake_interval_minutes"] * 60
        for t in triggers:
            if not isinstance(t, dict):
                continue
            tid = t.get("id") or json.dumps(t, sort_keys=True)
            # Optional not_before/not_after windows: a watch can expire
            # when it stops being actionable while protective triggers
            # stay unbounded. Malformed values FAIL OPEN — a typo must
            # never silently disarm a protective tripwire.
            if not self._in_window(t, tid):
                continue
            if time.time() - self.fired.get(tid, 0) < debounce:
                continue
            # One malformed trigger must never abort the loop: an
            # unhandled schema error here would blind EVERY sense —
            # quote polling, fill adoption, scanners — behind one typo.
            try:
                hit, detail = self.check(t, latest)
            except Exception as e:
                if tid not in self.warned_bad_triggers:
                    self.warned_bad_triggers.add(tid)
                    log(f"WARNING: trigger {tid} unevaluable ({e!r})")
                    self.ledger.record_event(
                        "sentinel", "trigger_unevaluable",
                        {"id": tid, "error": repr(e)})
                    # Fail LOUD to the AUTHOR: wake the agent so it can
                    # fix its own schema. A tripwire that cannot be
                    # evaluated has not been watching the market since it
                    # was armed — the author must know that before
                    # trusting any "it didn't fire" conclusion.
                    self.request_wake(
                        f"INERT TRIPWIRE {tid}: this trigger cannot be "
                        f"evaluated ({e!r}). It has NOT been watching the "
                        "market since it was armed. Fix its schema in "
                        "triggers.json (threshold key: `value`) and "
                        "re-verify with `trade events` before trusting "
                        "any 'didn't fire' conclusion.",
                        {"trigger": t, "error": repr(e)},
                        protective=bool(t.get("protective")))
                continue
            if hit:
                # Re-read triggers.json before firing: the agent may have
                # re-armed this trigger mid-loop and the copy in hand is
                # stale. Fire only what the file says NOW.
                if t.get("id"):
                    fresh = {ft["id"]: ft for ft in self.load_triggers()
                             if isinstance(ft, dict) and ft.get("id")}
                    cur = fresh.get(t["id"])
                    if cur is None or any(
                            cur.get(k) != t.get(k)
                            for k in ("type", "symbol", "value")):
                        log(f"stale trigger skipped: {tid}")
                        self.ledger.record_event(
                            "sentinel", "trigger_stale_skipped", {"id": tid})
                        continue
                self.fired[tid] = time.time()
                self.request_wake(
                    f"TRIGGER {tid}: {t.get('note') or t.get('type')}",
                    {"trigger": t, "detail": detail},
                    protective=bool(t.get("protective")),
                    wake_as=t)

    @staticmethod
    def _tval(t: dict):
        """The trigger threshold. `value` is canonical; the natural
        aliases authors actually reach for are accepted — a key-name
        slip must degrade to a synonym, never to an inert tripwire."""
        for k in ("value", "price", "threshold", "pct", "level"):
            if t.get(k) is not None:
                return t[k]
        return None

    # An unknown or MISSING type must RAISE (feeding the inert-tripwire
    # machinery above) — falling through to False is indistinguishable
    # from "armed and quiet", which is the worst failure a protective
    # layer can have. price_above_bid / price_below_ask evaluate against
    # the EXECUTABLE side of the book instead of LAST: in a thin book
    # LAST prints away from the touch, so LAST-keyed triggers false-fire.
    # An empty side never fires — you can't sell into no bid.
    KNOWN_TRIGGER_TYPES = ("price_above", "price_below", "pct_move",
                           "range_pct", "order_fill",
                           "price_above_bid", "price_below_ask")

    def check(self, t: dict, latest: dict[str, float]) -> tuple[bool, dict]:
        typ = t.get("type") or t.get("condition")
        if typ not in self.KNOWN_TRIGGER_TYPES:
            raise ValueError(
                f"unknown or missing trigger type {typ!r} — canonical key "
                f"`type`, one of {sorted(self.KNOWN_TRIGGER_TYPES)}")
        if typ == "order_fill" and not t.get("order_id"):
            raise ValueError(
                "order_fill trigger has no order_id — it can never fire")
        sym = t.get("symbol")
        px = latest.get(sym)
        val = self._tval(t)
        if typ != "order_fill" and val is None:
            raise ValueError(f"trigger has no value threshold: {typ}")
        if typ == "price_above" and px is not None:
            return px >= val, {"price": px}
        if typ == "price_below" and px is not None:
            return px <= val, {"price": px}
        if typ == "price_above_bid":
            bid = (self.latest_quotes.get(sym) or {}).get("bid") or 0.0
            if bid:
                return bid >= val, {"bid": bid, "last": px}
            return False, {}
        if typ == "price_below_ask":
            ask = (self.latest_quotes.get(sym) or {}).get("ask") or 0.0
            if ask:
                return ask <= val, {"ask": ask, "last": px}
            return False, {}
        if typ == "pct_move" and sym:
            mv = self.price_pct_move(sym, t.get("window_min", 15))
            return (mv is not None and abs(mv) >= val, {"pct_move": mv})
        if typ == "range_pct" and sym in self.day_range:
            r = self.day_range[sym]
            rng = (r["hi"] - r["lo"]) / r["lo"] * 100 if r["lo"] else 0
            return rng >= val, {"day_range_pct": rng, **r}
        if typ == "order_fill" and t.get("order_id"):
            try:
                o = self.venue.get_order(t["order_id"])
            except Exception:
                return False, {}
            if o["status"] == "filled":
                return bool(t.get("wake", True)), {"order": {
                    k: o[k] for k in ("status", "filled_qty",
                                      "filled_avg_price")}}
        return False, {}

    def _in_window(self, t: dict, tid: str) -> bool:
        for key in ("not_before", "not_after"):
            raw = t.get(key)
            if not raw:
                continue
            try:
                bound = datetime.fromisoformat(
                    str(raw).replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError):
                if tid not in self.warned_windows:
                    self.warned_windows.add(tid)
                    log(f"trigger {tid}: malformed {key}={raw!r} — "
                        "ignored (fail-open)")
                continue
            if (key == "not_after" and time.time() > bound) or \
                    (key == "not_before" and time.time() < bound):
                return False
        return True

    # -- fill adoption ---------------------------------------------------

    OPEN_ORDER_STATUSES = _OPEN_STATUSES

    def _adopt_mleg_fill(self, row: dict, o: dict) -> None:
        """A multi-leg order filled after its session ended: create one
        ledger trade per leg, grouped by the structure id, so per-leg
        exits and reviews stay representable."""
        legs = o.get("legs") or []
        try:
            intended = json.loads(row.get("legs") or "[]")
        except (TypeError, json.JSONDecodeError):
            intended = []
        by_symbol = {l.get("symbol"): l for l in intended
                     if isinstance(l, dict)}
        structure_id = row.get("structure_id") or row["venue_order_id"]
        tids = []
        for leg in legs:
            sym = leg.get("symbol")
            if not sym:
                continue
            side_raw = str(leg.get("side", "")).lower()
            side = "long" if "buy" in side_raw else "short"
            ratio = float((by_symbol.get(sym) or {}).get("ratio_qty") or 1)
            tids.append(self.ledger.open_trade(
                venue=row["venue"], symbol=sym, side=side,
                qty=float(leg.get("filled_qty") or (row["qty"] or 1) * ratio),
                entry_price=(float(leg["filled_avg_price"])
                             if leg.get("filled_avg_price") else None),
                thesis=row["thesis"] or "(sentinel-adopted spread fill)",
                structure_id=structure_id,
                session_id_open=row["session_id"],
                meta={"multiplier": 100}))
        self.ledger.update_order(row["id"], status="filled",
                                 filled_qty=o.get("filled_qty"),
                                 filled_avg_price=o.get("filled_avg_price"))
        self.ledger.record_event(
            "sentinel", "fill_adopted",
            {"order_id": row["venue_order_id"], "structure_id": structure_id,
             "legs": len(tids)})
        self.request_wake(
            f"SPREAD FILLED: your resting multi-leg order "
            f"({len(tids)} legs, structure {structure_id}) executed and the "
            "position is LIVE (ledger updated, one trade per leg). Wake: "
            "verify the structure landed as intended and arm any "
            "protection you want.",
            {"order_id": row["venue_order_id"], "trade_ids": tids},
            protective=True)
        log(f"mleg fill adopted: {row['venue_order_id']} -> {len(tids)} legs")

    def adopt_fills(self) -> None:
        """Resting orders fill AFTER the session that placed them has
        ended — nothing else closes that loop, so the sentinel does. The
        venue is the source of truth: adopt the fill into the ledger and
        wake the agent to protect/replan."""
        try:
            marks = ",".join("?" for _ in self.OPEN_ORDER_STATUSES)
            rows = self.ledger.query(
                "SELECT * FROM orders WHERE venue_order_id IS NOT NULL "
                f"AND status IN ({marks})", self.OPEN_ORDER_STATUSES)
        except Exception as e:
            log(f"fill adoption query error: {e!r}")
            return
        for row in rows:
            try:
                o = self.venue.get_order(row["venue_order_id"])
            except Exception:
                continue    # transient venue error; next poll retries
            status = (o.get("status") or "").lower()
            if status in ("canceled", "cancelled", "expired", "rejected",
                          "done_for_day", "replaced"):
                self.ledger.update_order(row["id"], status=status)
                log(f"fill adoption: order {row['venue_order_id']} "
                    f"-> {status}")
                continue
            if row["side"] == "mleg":
                if status == "filled":
                    self._adopt_mleg_fill(row, o)
                continue
            if status == "partially_filled":
                # A partial fill is a LIVE position: acting only on the
                # terminal status leaves real contracts ledger-invisible
                # for hours. Wake once per order on the FIRST partial;
                # later increments are events only.
                fq = o.get("filled_qty") or 0
                if fq and fq != (row["filled_qty"] or 0):
                    first = not row["filled_qty"]
                    px = o.get("filled_avg_price")
                    self.ledger.update_order(
                        row["id"], filled_qty=fq,
                        filled_avg_price=px, fees=o.get("fees") or 0)
                    if row["trade_id"]:
                        t = self.ledger.query(
                            "SELECT * FROM trades WHERE id=?",
                            (row["trade_id"],))
                        t = t[0] if t else None
                        if t and t["status"] == "open" and \
                                (t["side"] == "long") == (row["side"] == "buy"):
                            kw = {"qty": fq}
                            if px:
                                kw["entry_price"] = px
                            self.ledger.update_trade(t["id"], **kw)
                    else:
                        side = "long" if row["side"] == "buy" else "short"
                        tid = self.ledger.open_trade(
                            venue=row["venue"], symbol=row["symbol"],
                            side=side, qty=fq, entry_price=px,
                            fees=o.get("fees") or 0,
                            thesis=row["thesis"]
                            or "(sentinel-adopted partial fill)",
                            session_id_open=row["session_id"],
                            meta={"multiplier": 100}
                            if OCC_RE.match(row["symbol"]) else None)
                        self.ledger.update_order(row["id"], trade_id=tid)
                    self.ledger.record_event(
                        "sentinel", "partial_fill_adopted",
                        {"order_id": row["venue_order_id"],
                         "symbol": row["symbol"], "filled_qty": fq,
                         "filled_avg_price": px, "order_qty": row["qty"]})
                    log(f"partial fill adopted: {row['symbol']} "
                        f"{row['side']} {fq}/{row['qty']} @ {px}")
                    if first:
                        self.request_wake(
                            f"PARTIAL FILL: {row['side']} {fq} of "
                            f"{row['qty']} {row['symbol']} @ {px} — your "
                            "resting order is filling and the position is "
                            "PARTIALLY LIVE (ledger updated; the remainder "
                            "is still working). Wake: verify protection "
                            "covers the live quantity and decide whether "
                            "the remainder should keep resting.",
                            {"order_id": row["venue_order_id"],
                             "trade_id": row["trade_id"],
                             "filled_qty": fq},
                            protective=True)
                continue
            if status != "filled":
                continue
            px = o.get("filled_avg_price")
            fq = o.get("filled_qty") or row["qty"]
            fees = o.get("fees") or 0
            self.ledger.update_order(row["id"], status="filled",
                                     filled_qty=fq, filled_avg_price=px,
                                     fees=fees)
            if row["trade_id"]:
                t = self.ledger.query("SELECT * FROM trades WHERE id=?",
                                      (row["trade_id"],))
                t = t[0] if t else None
                if not t:
                    continue
                closing = (t["side"] == "long") == (row["side"] == "sell")
                if closing and t["status"] == "open":
                    s = self.ledger.close_trade(
                        t["id"], exit_price=px, fees_add=fees,
                        exit_reason=((row["thesis"]
                                      or f"resting {row['order_type']} "
                                         "exit filled")
                                     + " (sentinel-adopted)"),
                        session_id=None)
                    self.request_wake(
                        f"ORDER FILLED (exit): your resting "
                        f"{row['order_type']} on {t['symbol']} executed @ "
                        f"{px} — position closed, PnL ${s['pnl']:,.2f}. "
                        "Wake: prune stale triggers, reassess, replan.",
                        {"order_id": row["venue_order_id"],
                         "trade_id": t["id"]}, protective=True)
                elif t["status"] == "open":
                    # Same-direction fill: the opening order completed
                    # late. Never clobber a real entry price with None,
                    # and WAKE the agent — a completion can be a large
                    # position change that filled on someone else's
                    # newer information.
                    kw = {"qty": fq}
                    if px:
                        kw["entry_price"] = px
                    self.ledger.update_trade(t["id"], **kw)
                    self.request_wake(
                        f"ORDER COMPLETED: your resting entry on "
                        f"{t['symbol']} finished filling — {t['side']} "
                        f"position is now {fq} @ {px} (ledger updated). "
                        "Wake: re-verify protection at the NEW size and "
                        "re-check the thesis.",
                        {"order_id": row["venue_order_id"],
                         "trade_id": t["id"], "filled_qty": fq},
                        protective=True)
            else:
                side = "long" if row["side"] == "buy" else "short"
                tid = self.ledger.open_trade(
                    venue=row["venue"], symbol=row["symbol"], side=side,
                    qty=fq, entry_price=px, fees=fees,
                    thesis=row["thesis"] or ("(sentinel-adopted fill — "
                                             "order carried no thesis)"),
                    session_id_open=row["session_id"],
                    meta={"multiplier": 100}
                    if OCC_RE.match(row["symbol"]) else None)
                self.ledger.update_order(row["id"], trade_id=tid)
                self.request_wake(
                    f"ORDER FILLED: {side} {fq} {row['symbol']} @ {px} — "
                    "your resting order executed and the position is LIVE "
                    "(ledger updated). Wake: verify any protection you "
                    "intend, then update state files.",
                    {"order_id": row["venue_order_id"], "trade_id": tid},
                    protective=True)
            self.ledger.record_event(
                "sentinel", "fill_adopted",
                {"order_id": row["venue_order_id"],
                 "symbol": row["symbol"],
                 "filled_avg_price": px, "qty": fq})
            log(f"fill adopted: {row['symbol']} {row['side']} {fq} @ {px}")

    # -- housekeeping ----------------------------------------------------

    def housekeeping(self) -> None:
        s = self.cfg.get("sentinel") or {}
        now = time.time()

        if s.get("balance_snapshot_minutes", 60) and \
                now - self.last_balance > \
                s.get("balance_snapshot_minutes", 60) * 60:
            self.last_balance = now
            try:
                a = self.venue.account()
                self.ledger.record_balance(a["equity"], a["cash"],
                                           a["positions_value"])
            except Exception as e:
                log(f"balance snapshot error: {e!r}")

        alarm_h = s.get("heartbeat_alarm_hours", 26)
        last = self.ledger.last_session_ts()
        halted = (self.state / "HALT").exists()
        gap_h = 24 if halted else 6
        if alarm_h and last and (now - last) > alarm_h * 3600 \
                and now - self.last_heartbeat_alarm > gap_h * 3600:
            self.last_heartbeat_alarm = now
            try:
                (self.state / ".heartbeat_alarm_ts").write_text(str(now))
            except OSError:
                pass
            quiet_h = int((now - last) / 3600)
            log(f"heartbeat alarm: no session in {quiet_h}h"
                + (" (halted — expected)" if halted else ""))
            self.ledger.record_event(
                "sentinel", "heartbeat_alarm",
                {"halted": halted, "hours_since_session": quiet_h})

        (self.state / "sentinel_heartbeat").write_text(str(now))

    # -- main loop -------------------------------------------------------

    def run(self) -> None:
        poll = (self.cfg.get("sentinel") or {}).get("quote_poll_seconds", 15)
        log(f"sentinel up: poll={poll}s")
        while True:
            try:
                triggers = self.load_triggers()
                symbols = self.watched_symbols(triggers)
                latest = self.poll_quotes(symbols)
                self.evaluate(triggers, latest)
                self.adopt_fills()
                if self.scanners:
                    self.scanners.tick(time.time())
                self.housekeeping()
            except Exception as e:
                log(f"loop error: {e!r}")
                self.ledger.record_event("sentinel", "error", repr(e))
            time.sleep(poll)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    Sentinel(cfg).run()


if __name__ == "__main__":
    main()
