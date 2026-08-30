import { appendFile, mkdir, readdir, stat, unlink } from "node:fs/promises";
import path from "node:path";

/**
 * The web app's own structured event logger (server-side only).
 *
 * Appends one JSON line per event to the UI's daily log stream at
 * `$UI_LOGS_DIR/daily/<YYYY-MM-DD>.jsonl` (day in UTC), the same stream
 * the Logs page renders. Record shape mirrors the rest of the system:
 * {ts, level, component: "web", event, ...key-values}.
 *
 * Logging must never break a request path: this function never throws
 * and silently no-ops when UI_LOGS_DIR is unset or the write fails.
 *
 * Logging must also never fill the disk. Same self-enforcing bounds as
 * the engine's logger, same env overrides: a per-day file byte cap
 * (JSONLOG_MAX_FILE_MB — once exceeded, one "log_file_capped" marker
 * is written and the rest of the day's records are dropped), a
 * total-directory byte cap (JSONLOG_MAX_TOTAL_MB, oldest days deleted
 * first, newest kept), and day-count retention (JSONLOG_KEEP_DAYS).
 * Retention runs on day rollover inside the writer, so no external
 * housekeeping is a single point of disk-safety failure.
 */

export type LogLevel = "debug" | "info" | "warn" | "error";

const num = (v: string | undefined, dflt: number) => {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : dflt;
};
const MAX_FILE_BYTES = num(process.env.JSONLOG_MAX_FILE_MB, 64) * 1024 * 1024;
const MAX_TOTAL_BYTES = num(process.env.JSONLOG_MAX_TOTAL_MB, 512) * 1024 * 1024;
const KEEP_DAYS = num(process.env.JSONLOG_KEEP_DAYS, 7);

const DAY_FILE = /^\d{4}-\d{2}-\d{2}\.jsonl$/;

// Per-process state for the safety bounds. A restart resets it, which
// only means one extra stat/prune — never a correctness problem.
let lastDay = "";
let cappedToday = false;

async function prune(dailyDir: string): Promise<void> {
  const cutoff = new Date(Date.now() - KEEP_DAYS * 86400_000)
    .toISOString()
    .slice(0, 10);
  // YYYY-MM-DD names sort chronologically.
  const names = (await readdir(dailyDir)).filter((n) => DAY_FILE.test(n)).sort();
  const kept: { file: string; size: number }[] = [];
  for (const n of names) {
    const file = path.join(dailyDir, n);
    if (n.slice(0, 10) < cutoff) {
      await unlink(file).catch(() => undefined);
    } else {
      const size = await stat(file).then((s) => s.size).catch(() => 0);
      kept.push({ file, size });
    }
  }
  let total = kept.reduce((a, f) => a + f.size, 0);
  for (let i = 0; total > MAX_TOTAL_BYTES && i < kept.length - 1; i++) {
    await unlink(kept[i].file).catch(() => undefined);
    total -= kept[i].size;
  }
}

async function write(dailyDir: string, file: string, line: string): Promise<void> {
  await mkdir(dailyDir, { recursive: true });
  const size = await stat(file).then((s) => s.size).catch(() => 0);
  if (size >= MAX_FILE_BYTES) {
    if (!cappedToday) {
      cappedToday = true;
      const marker = JSON.stringify({
        ts: new Date().toISOString(),
        level: "warn",
        component: "web",
        event: "log_file_capped",
        limit_mb: MAX_FILE_BYTES / 1024 / 1024,
        note: "daily file reached its byte cap; further records today are dropped",
      });
      await appendFile(file, `${marker}\n`, "utf8");
    }
    return;
  }
  await appendFile(file, line, "utf8");
}

export function logEvent(
  level: LogLevel,
  event: string,
  kv?: Record<string, unknown>
): void {
  try {
    const dir = process.env.UI_LOGS_DIR;
    if (!dir) return;

    const now = new Date();
    const day = now.toISOString().slice(0, 10);
    const record = {
      ts: now.toISOString(),
      level,
      component: "web",
      event,
      ...kv,
    };

    const dailyDir = path.join(dir, "daily");
    const file = path.join(dailyDir, `${day}.jsonl`);
    const line = `${JSON.stringify(record)}\n`;

    if (day !== lastDay) {
      lastDay = day;
      cappedToday = false;
      void prune(dailyDir).catch(() => undefined);
    }

    // Fire-and-forget: the request never waits on (or fails with) the log.
    void write(dailyDir, file, line).catch(() => undefined);
  } catch {
    // Never throw from the logger.
  }
}
