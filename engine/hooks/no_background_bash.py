#!/usr/bin/env python3
"""PreToolUse hook: block backgrounded Bash in headless agent sessions.

Headless sessions END the moment the model stops calling tools — a
backgrounded task dies with the session, and any "you will be notified
when it completes" tool text is FALSE here (it is written for
interactive mode). A prompt warning alone does not hold: the in-context
tool result out-argues it. Enforcement beats advice.

Known gap (accepted): a mid-command single `&` inside a longer shell string
can still background a child. Parsing shell is not worth the false positives;
run_in_background + trailing-& + nohup/setsid cover the observed patterns.

Contract (Claude Code hooks): PreToolUse JSON arrives on stdin; exit code 2
blocks the tool call and feeds stderr back to the model; exit 0 allows.
"""
import json
import re
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0            # malformed input: never block on doubt
    if payload.get("tool_name") != "Bash":
        return 0
    ti = payload.get("tool_input") or {}
    cmd = (ti.get("command") or "").rstrip()
    backgrounded = bool(ti.get("run_in_background"))
    if not backgrounded:
        if re.search(r"(^|[;&|(]\s*|\s)(nohup|setsid)\s", cmd):
            backgrounded = True
        elif cmd.endswith("&") and not cmd.endswith("&&"):
            backgrounded = True
    if not backgrounded:
        return 0
    sys.stderr.write(
        "BLOCKED (engine policy): background tasks are disabled in these "
        "headless sessions. Your session ends the moment you stop calling "
        "tools — a backgrounded task dies with it and can NEVER notify or "
        "re-invoke you; any 'you will be notified' text does not apply "
        "here. Instead: do the work in the FOREGROUND (a loop with sleeps "
        "inside one Bash call is fine — raise `timeout` up to 600000 ms), "
        "or split it across wakes: place the order / arm triggers.json, "
        "write your schedule, and let the sentinel wake you.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
