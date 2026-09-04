# Logging — the system's nervous system

*Written for the AI assistant. When anything behaves unexpectedly, the
logs are where the answer lives — every component narrates its
decisions in a machine-readable stream designed for exactly the reader
you are.*

## The streams

Every component writes structured JSONL, split by UTC day, alongside
its human-readable journald stream:

- **Mind side:** `/srv/mind/logs/daily/YYYY-MM-DD.jsonl` — components
  `supervisor`, `sentinel`, `scanners`, `trade`, `venue`, `ledger`.
- **UI side:** `/srv/ui/logs/daily/YYYY-MM-DD.jsonl` — components
  `supervisor` (the UI manager's engine) and `web` (the Next.js app).

Each record: `ts`, `level` (`debug|info|warn|error`), `component`,
`event` (snake_case), plus key-values — errors carry `error` and
`trace`, and trade activity carries `session_id` so a line correlates
to the agent session that caused it.

**Start with the Logs page in the UI** (Mind / UI tabs): day picker,
level and component filters, search, expandable records, and a live
tail. From a shell, `jq` over a daily file answers anything:

```bash
run "jq -r 'select(.level==\"error\")' /srv/mind/logs/daily/$(date -u +%F).jsonl"
run "jq -r 'select(.component==\"supervisor\")|.event' /srv/mind/logs/daily/$(date -u +%F).jsonl | sort | uniq -c"
```

## The events worth knowing

The lifecycle backbone, per side: `startup` → wake decisions
(`slot_due`, `wake_request_serviced`, `one_shot_wake`,
`backstop_fired`, `notify_wake`…) → `session_launch` →
`session_finish` (exit code, turns, duration — never tokens or cost;
economics are not logged anywhere an agent reads). Trading truth:
`order_intent_recorded` → `order_placed` → `fill_adopted` /
`order_terminal`; `trigger_fire` and `scanner_fire` for the sensors;
`unrecorded_fill` is the loud failsafe that deserves immediate
attention if it ever appears.

## Levels and filtering

`LOG_LEVEL` (env, default `info`) filters only the journald stream;
the daily files always receive every level, debug included — the
record that explains a failure is usually written before anyone knows
a failure is coming. Debug rows carry the per-tick mechanics (quote
polls, quiet trigger evaluations, per-REST-call timings).

## Disk safety — the logs cannot fill the disk, by construction

Three self-enforcing bounds (env-overridable): a per-day file cap
(`JSONLOG_MAX_FILE_MB`, 64 — a runaway loop hits the ceiling, one
`log_file_capped` marker is written, the rest of that day's records
drop from the file while journald keeps flowing), a total-directory
cap (`JSONLOG_MAX_TOTAL_MB`, 512 — oldest days deleted first), and
retention (`JSONLOG_KEEP_DAYS`, 7). Retention and the directory cap
enforce themselves on day rollover inside every writer — Python engine
and web app alike — so no housekeeping job is a single point of
disk-safety failure. journald (`journalctl -u <unit>`) remains the
operator's low-level view, has its own systemd size caps, and survives
even a broken file sink.

## What is never in a log

Keys, tokens, auth headers, `.env` contents. Log calls are written to
never receive them, and the venue layer logs paths and statuses but
never headers. A log stream you can safely show anyone is the point.
