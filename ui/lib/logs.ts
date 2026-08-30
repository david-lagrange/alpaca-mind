import { open, readdir } from "node:fs/promises";
import path from "node:path";

/**
 * Read-side access to the two structured log streams on this host.
 *
 * Both the trading engine ("mind") and this web app ("ui") write daily
 * JSONL files — one JSON record per line — under `<dir>/daily/` where
 * `<dir>` comes from MIND_LOGS_DIR / UI_LOGS_DIR. The mind stream is
 * read-only here; the ui stream is also written by lib/log.ts.
 *
 * Safety invariants:
 *   - Paths are derived ONLY from the env-configured directory, the fixed
 *     source map, and a strictly validated YYYY-MM-DD day string. No
 *     caller-supplied path fragment ever reaches the filesystem.
 *   - Reads are bounded per request by both an entry limit and a byte
 *     ceiling, so an arbitrarily large day file cannot exhaust memory.
 *   - Missing directories/files degrade to empty results, never throws.
 *
 * Tailing works through `cursor`, a byte offset into the day file: a
 * caller re-reads from its last cursor to receive only appended lines.
 */

export type LogSource = "mind" | "ui";

export type LogRecord = Record<string, unknown>;

export interface ReadDayOptions {
  /** Levels to include; absent means all levels. */
  levels?: string[];
  /** Components to include; absent means all components. */
  components?: string[];
  /** Case-insensitive substring match against the raw line. */
  q?: string;
  /** Byte offset to resume reading from (0 = start of file). */
  cursor?: number;
  /** Max entries to return (default 300, capped at 1000). */
  limit?: number;
}

export interface ReadDayResult {
  entries: LogRecord[];
  /** Byte offset after the last consumed line; pass back to continue. */
  cursor: number;
  /** True when the read consumed everything currently in the file. */
  eof: boolean;
  /** Distinct components seen among the lines scanned (pre-filter). */
  components: string[];
}

const DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const DAY_FILE_PATTERN = /^\d{4}-\d{2}-\d{2}\.jsonl$/;
const DEFAULT_LIMIT = 300;
const MAX_LIMIT = 1000;
/** Per-request read ceiling in bytes. */
const BYTE_CEILING = 2 * 1024 * 1024;

/** Log directory for a source from env; null when not configured. */
export function logDirFor(source: LogSource): string | null {
  const dir =
    source === "mind" ? process.env.MIND_LOGS_DIR : process.env.UI_LOGS_DIR;
  return dir && dir.trim().length > 0 ? dir : null;
}

/** Days with a log file for the source, as YYYY-MM-DD, newest first. */
export async function listDays(source: LogSource): Promise<string[]> {
  const dir = logDirFor(source);
  if (!dir) return [];
  try {
    const names = await readdir(path.join(dir, "daily"));
    return names
      .filter((name) => DAY_FILE_PATTERN.test(name))
      .map((name) => name.slice(0, 10))
      .sort()
      .reverse();
  } catch {
    return [];
  }
}

const emptyResult = (cursor: number): ReadDayResult => ({
  entries: [],
  cursor,
  eof: true,
  components: [],
});

/**
 * Read one day's log file from a byte cursor, applying filters, bounded
 * by an entry limit and a byte ceiling. Malformed lines are skipped.
 */
export async function readDay(
  source: LogSource,
  day: string,
  opts: ReadDayOptions = {}
): Promise<ReadDayResult> {
  // Strict validation before the value participates in a path.
  if (!DAY_PATTERN.test(day)) {
    throw new Error("Invalid day format; expected YYYY-MM-DD.");
  }

  const dir = logDirFor(source);
  const startCursor = clampCursor(opts.cursor);
  if (!dir) return emptyResult(startCursor);

  const limit = clampLimit(opts.limit);
  const levelSet = toLowerSet(opts.levels);
  const componentSet = toLowerSet(opts.components);
  const query = opts.q ? opts.q.toLowerCase() : null;

  const file = path.join(dir, "daily", `${day}.jsonl`);

  let handle;
  try {
    handle = await open(file, "r");
  } catch {
    // Missing file (or unreadable) is a legitimate empty day.
    return emptyResult(startCursor);
  }

  try {
    const { size } = await handle.stat();
    const offset = Math.min(startCursor, size);
    const toRead = Math.min(BYTE_CEILING, size - offset);
    if (toRead <= 0) {
      return { entries: [], cursor: offset, eof: offset >= size, components: [] };
    }

    const buffer = Buffer.alloc(toRead);
    const { bytesRead } = await handle.read(buffer, 0, toRead, offset);

    const entries: LogRecord[] = [];
    const componentsSeen = new Set<string>();
    let pos = 0;
    let consumed = 0;

    while (pos < bytesRead && entries.length < limit) {
      const newline = buffer.indexOf(10, pos);
      if (newline === -1 || newline >= bytesRead) break; // incomplete line
      const rawLine = buffer.subarray(pos, newline).toString("utf8");
      pos = newline + 1;
      consumed = pos;

      const trimmed = rawLine.trim();
      if (trimmed.length === 0) continue;

      let record: LogRecord;
      try {
        const parsed: unknown = JSON.parse(trimmed);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          continue;
        }
        record = parsed as LogRecord;
      } catch {
        continue; // tolerate malformed lines
      }

      const component =
        typeof record.component === "string" ? record.component : "";
      if (component) componentsSeen.add(component);

      const level = typeof record.level === "string" ? record.level : "";
      if (levelSet && !levelSet.has(level.toLowerCase())) continue;
      if (componentSet && !componentSet.has(component.toLowerCase())) continue;
      if (query && !trimmed.toLowerCase().includes(query)) continue;

      entries.push(record);
    }

    const cursor = offset + consumed;
    const eof = cursor >= size;
    return {
      entries,
      cursor,
      eof,
      components: Array.from(componentsSeen).sort(),
    };
  } catch {
    return emptyResult(startCursor);
  } finally {
    await handle.close().catch(() => undefined);
  }
}

function clampCursor(cursor: number | undefined): number {
  if (typeof cursor !== "number" || !Number.isFinite(cursor) || cursor < 0) {
    return 0;
  }
  return Math.floor(cursor);
}

function clampLimit(limit: number | undefined): number {
  if (typeof limit !== "number" || !Number.isFinite(limit) || limit < 1) {
    return DEFAULT_LIMIT;
  }
  return Math.min(Math.floor(limit), MAX_LIMIT);
}

function toLowerSet(values: string[] | undefined): Set<string> | null {
  if (!values) return null;
  const set = new Set(
    values.map((v) => v.trim().toLowerCase()).filter((v) => v.length > 0)
  );
  return set.size > 0 ? set : null;
}
