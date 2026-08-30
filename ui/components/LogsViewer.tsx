"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/**
 * Shared viewer for one structured log source (mind | ui).
 *
 * Reads /api/logs: meta first (which days exist, today's UTC day), then
 * pages through the selected day with a byte cursor. When the selected
 * day is the current UTC day it tails the file — polling with the last
 * cursor so only appended lines travel — pausing while the tab is
 * hidden. Filters (level, component, search) are applied server-side;
 * a row expands to the pretty-printed full record.
 */

type LogRecord = Record<string, unknown>;

interface Meta {
  configured: boolean;
  days: string[];
  today: string;
}

interface LogPage {
  configured: boolean;
  entries: LogRecord[];
  cursor: number;
  eof: boolean;
  components: string[];
}

const LEVELS = ["debug", "info", "warn", "error"] as const;
type Level = (typeof LEVELS)[number];

const LEVEL_TEXT: Record<Level, string> = {
  debug: "text-faint",
  info: "text-muted",
  warn: "text-warn",
  error: "text-loss",
};

const SKIP_KEYS = new Set(["ts", "level", "component", "event", "trace"]);
const PAGE_LIMIT = 1000;
/** Pages fetched automatically per (re)load before offering "load more". */
const AUTO_PAGES = 3;
const POLL_MS = 5000;
const DEBOUNCE_MS = 300;
/** Distance from the bottom (px) still counted as "at the bottom". */
const BOTTOM_SLACK = 40;

function isLevel(value: unknown): value is Level {
  return typeof value === "string" && (LEVELS as readonly string[]).includes(value);
}

function localTime(ts: unknown): string {
  if (typeof ts !== "string") return "--:--:--";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "--:--:--";
  return d.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function kvPairs(record: LogRecord): [string, unknown][] {
  return Object.entries(record).filter(([key]) => !SKIP_KEYS.has(key));
}

function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function Chip({
  label,
  active,
  activeClass,
  onClick,
}: {
  label: string;
  active: boolean;
  activeClass: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-3 py-1.5 font-mono text-xs transition-colors ${
        active
          ? `border-edge bg-raised ${activeClass}`
          : "border-edge/60 text-faint hover:text-muted"
      }`}
    >
      {label}
    </button>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-edge p-6 text-center text-sm text-faint">
      {children}
    </div>
  );
}

export default function LogsViewer({ source }: { source: "mind" | "ui" }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState(false);
  const [day, setDay] = useState<string | null>(null);

  const [levels, setLevels] = useState<Set<Level>>(
    () => new Set<Level>(["info", "warn", "error"])
  );
  const [knownComponents, setKnownComponents] = useState<string[]>([]);
  const [excluded, setExcluded] = useState<Set<string>>(() => new Set());
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");

  const [entries, setEntries] = useState<LogRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [truncated, setTruncated] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [hidden, setHidden] = useState(false);
  const [pinned, setPinned] = useState(true);
  const [, setTick] = useState(0);

  const cursorRef = useRef(0);
  const generationRef = useRef(0);
  const inFlightRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const programmaticScrollRef = useRef(false);
  const pinnedRef = useRef(true);
  pinnedRef.current = pinned;

  const levelsKey = useMemo(() => [...levels].sort().join(","), [levels]);
  const excludedKey = useMemo(() => [...excluded].sort().join(","), [excluded]);

  const dayOptions = useMemo(() => {
    if (!meta || !meta.configured || meta.days.length === 0) return [];
    // Today is always offered so an empty live day can still be tailed.
    return Array.from(new Set([meta.today, ...meta.days])).sort().reverse();
  }, [meta]);

  const isLiveDay = Boolean(meta?.configured && day && day === meta.today);

  /** Components to request: all when nothing is excluded. */
  const includedComponents = useMemo(() => {
    if (excluded.size === 0) return null;
    return knownComponents.filter((c) => !excluded.has(c));
  }, [excluded, knownComponents]);

  const buildUrl = useCallback(
    (cursor: number) => {
      const params = new URLSearchParams({
        source,
        day: day ?? "",
        levels: [...levels].sort().join(","),
        cursor: String(cursor),
        limit: String(PAGE_LIMIT),
      });
      if (includedComponents !== null) {
        params.set("components", includedComponents.join(","));
      }
      if (q) params.set("q", q);
      return `/api/logs?${params.toString()}`;
    },
    [source, day, levels, includedComponents, q]
  );

  const fetchPage = useCallback(
    async (cursor: number): Promise<LogPage> => {
      const response = await fetch(buildUrl(cursor), { cache: "no-store" });
      if (!response.ok) throw new Error(`status ${response.status}`);
      return (await response.json()) as LogPage;
    },
    [buildUrl]
  );

  const mergeComponents = useCallback((seen: Iterable<string>) => {
    setKnownComponents((prev) => {
      const merged = new Set(prev);
      let grew = false;
      for (const component of seen) {
        if (!merged.has(component)) {
          merged.add(component);
          grew = true;
        }
      }
      return grew ? Array.from(merged).sort() : prev;
    });
  }, []);

  /* Meta: which days exist, and what "today" (UTC) currently is. */
  useEffect(() => {
    let cancelled = false;
    setMeta(null);
    setMetaError(false);
    setDay(null);
    setEntries([]);
    setKnownComponents([]);
    setExcluded(new Set());
    fetch(`/api/logs?source=${source}&meta=1`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`status ${response.status}`);
        return response.json() as Promise<Meta>;
      })
      .then((m) => {
        if (cancelled) return;
        setMeta(m);
        if (m.configured && m.days.length > 0) {
          setDay(m.days.includes(m.today) ? m.today : m.days[0]);
        } else if (m.configured) {
          setDay(null);
        }
      })
      .catch(() => {
        if (!cancelled) setMetaError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [source]);

  /* Full (re)load whenever the day or any filter changes. */
  useEffect(() => {
    if (!meta?.configured || !day) return;
    const generation = ++generationRef.current;
    cursorRef.current = 0;
    setEntries([]);
    setExpanded(null);
    setLoadError(false);
    setTruncated(false);
    setLoading(true);

    // Every component excluded means an intentionally empty view.
    if (includedComponents !== null && includedComponents.length === 0) {
      setLoading(false);
      return;
    }

    (async () => {
      try {
        let cursor = 0;
        let collected: LogRecord[] = [];
        const seen = new Set<string>();
        let eof = false;
        for (let page = 0; page < AUTO_PAGES; page++) {
          const result = await fetchPage(cursor);
          if (generation !== generationRef.current) return;
          collected = collected.concat(result.entries);
          result.components.forEach((c) => seen.add(c));
          cursor = result.cursor;
          eof = result.eof;
          if (eof) break;
        }
        cursorRef.current = cursor;
        setEntries(collected);
        mergeComponents(seen);
        setTruncated(!eof);
        setLastUpdated(Date.now());
      } catch {
        if (generation === generationRef.current) setLoadError(true);
      } finally {
        if (generation === generationRef.current) setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta, day, levelsKey, excludedKey, q, source]);

  /* Continue from the current cursor (manual "load more"). */
  const loadMore = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    const generation = generationRef.current;
    setLoadingMore(true);
    try {
      const result = await fetchPage(cursorRef.current);
      if (generation !== generationRef.current) return;
      cursorRef.current = result.cursor;
      if (result.entries.length > 0) {
        setEntries((prev) => prev.concat(result.entries));
      }
      mergeComponents(result.components);
      setTruncated(!result.eof);
      setLastUpdated(Date.now());
    } catch {
      if (generation === generationRef.current) setLoadError(true);
    } finally {
      inFlightRef.current = false;
      if (generation === generationRef.current) setLoadingMore(false);
    }
  }, [fetchPage, mergeComponents]);

  /* Live tail: poll the cursor while viewing today's file. */
  useEffect(() => {
    if (!isLiveDay) return;
    const id = setInterval(() => {
      if (document.hidden || loading || inFlightRef.current) return;
      if (includedComponents !== null && includedComponents.length === 0) return;
      void loadMore();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [isLiveDay, loading, loadMore, includedComponents]);

  /* Pause indicator + a 1s tick so "updated Xs ago" stays honest. */
  useEffect(() => {
    const onVisibility = () => setHidden(document.hidden);
    onVisibility();
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  useEffect(() => {
    if (!isLiveDay) return;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [isLiveDay]);

  /* Search debounce. */
  useEffect(() => {
    const id = setTimeout(() => setQ(qInput.trim()), DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [qInput]);

  /* Auto-follow: keep the view pinned to the newest line. */
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !pinnedRef.current) return;
    programmaticScrollRef.current = true;
    el.scrollTop = el.scrollHeight;
  }, [entries]);

  const onScroll = useCallback(() => {
    if (programmaticScrollRef.current) {
      programmaticScrollRef.current = false;
      return;
    }
    const el = scrollRef.current;
    if (!el) return;
    const atBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < BOTTOM_SLACK;
    setPinned(atBottom);
  }, []);

  const togglePin = useCallback(() => {
    setPinned((prev) => {
      const next = !prev;
      if (next && scrollRef.current) {
        programmaticScrollRef.current = true;
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
      return next;
    });
  }, []);

  const toggleLevel = (level: Level) => {
    setLevels((prev) => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  };

  const toggleComponent = (component: string) => {
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(component)) next.delete(component);
      else next.add(component);
      return next;
    });
  };

  /* ---- top-level states ---- */

  if (metaError) {
    return <Notice>Couldn&apos;t reach the log source.</Notice>;
  }
  if (!meta) {
    return <Notice>Loading…</Notice>;
  }
  if (!meta.configured) {
    return (
      <Notice>
        Log source not configured —{" "}
        <span className="font-mono">
          {source === "mind" ? "MIND_LOGS_DIR" : "UI_LOGS_DIR"}
        </span>{" "}
        is unset on this deployment.
      </Notice>
    );
  }
  if (dayOptions.length === 0) {
    return <Notice>No logs yet — nothing has run on this side.</Notice>;
  }

  const filtersActive = q.length > 0 || excluded.size > 0 || levels.size < LEVELS.length;
  const secondsAgo =
    lastUpdated !== null ? Math.max(0, Math.round((Date.now() - lastUpdated) / 1000)) : null;

  return (
    <div>
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={day ?? ""}
          onChange={(e) => setDay(e.target.value)}
          className="rounded-md border border-edge bg-raised px-3 py-1.5 font-mono text-xs text-ink focus:border-accent focus:outline-none"
          aria-label="Log day (UTC)"
        >
          {dayOptions.map((d) => (
            <option key={d} value={d}>
              {d}
              {d === meta.today ? " (today)" : ""}
            </option>
          ))}
        </select>

        <div className="flex flex-wrap gap-1.5">
          {LEVELS.map((level) => (
            <Chip
              key={level}
              label={level}
              active={levels.has(level)}
              activeClass={LEVEL_TEXT[level]}
              onClick={() => toggleLevel(level)}
            />
          ))}
        </div>

        <input
          type="search"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          placeholder="Search lines…"
          className="min-w-[10rem] flex-1 rounded-md border border-edge bg-raised px-3 py-1.5 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none"
          aria-label="Search log lines"
        />
      </div>

      {knownComponents.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {knownComponents.map((component) => (
            <Chip
              key={component}
              label={component}
              active={!excluded.has(component)}
              activeClass="text-muted"
              onClick={() => toggleComponent(component)}
            />
          ))}
        </div>
      )}

      {/* Status row */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-faint">
        <p>
          <span className="font-mono text-muted">{entries.length}</span>{" "}
          {entries.length === 1 ? "entry" : "entries"} · day is UTC · times
          are local
        </p>
        <div className="flex items-center gap-3">
          {isLiveDay &&
            (hidden ? (
              <span>paused</span>
            ) : (
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-gain" />
                live
                {secondsAgo !== null && ` — updated ${secondsAgo}s ago`}
              </span>
            ))}
          {isLiveDay && (
            <button
              type="button"
              onClick={togglePin}
              aria-pressed={pinned}
              className={`rounded-md border px-2 py-1 font-mono transition-colors ${
                pinned
                  ? "border-accent/50 text-accent"
                  : "border-edge text-faint hover:text-muted"
              }`}
            >
              {pinned ? "following" : "follow"}
            </button>
          )}
        </div>
      </div>

      {/* Line area */}
      <div className="mt-2 rounded-lg border border-edge bg-surface">
        {loading ? (
          <p className="p-6 text-center text-sm text-faint">Loading…</p>
        ) : loadError ? (
          <div className="p-6 text-center text-sm text-faint">
            <p>Couldn&apos;t reach the log source.</p>
            <button
              type="button"
              onClick={() => {
                setLoadError(false);
                void loadMore();
              }}
              className="mt-2 rounded-md border border-edge px-3 py-1 text-xs text-muted hover:text-ink"
            >
              Retry
            </button>
          </div>
        ) : entries.length === 0 ? (
          <p className="p-6 text-center text-sm text-faint">
            {filtersActive
              ? "Nothing matches these filters."
              : isLiveDay
                ? "No entries yet today."
                : "No entries for this day."}
          </p>
        ) : (
          <div
            ref={scrollRef}
            onScroll={onScroll}
            className="max-h-[65vh] overflow-auto p-1 font-mono text-xs"
          >
            {entries.map((record, index) => {
              const level = isLevel(record.level) ? record.level : "info";
              const isOpen = expanded === index;
              return (
                <div key={index}>
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : index)}
                    aria-expanded={isOpen}
                    className={`flex w-full items-baseline gap-2 whitespace-nowrap rounded px-2 py-1 text-left transition-colors hover:bg-raised ${
                      isOpen ? "bg-raised" : ""
                    }`}
                  >
                    <span className="text-faint">{localTime(record.ts)}</span>
                    <span className={`w-12 shrink-0 uppercase ${LEVEL_TEXT[level]}`}>
                      {level}
                    </span>
                    <span className="text-faint">
                      {typeof record.component === "string"
                        ? record.component
                        : "?"}
                    </span>
                    <span className="text-ink">
                      {typeof record.event === "string" ? record.event : "—"}
                    </span>
                    <span className="text-muted">
                      {kvPairs(record).map(([key, value]) => (
                        <span key={key} className="mr-2">
                          <span className="text-faint">{key}=</span>
                          {formatValue(value)}
                        </span>
                      ))}
                    </span>
                  </button>
                  {isOpen && (
                    <pre className="mx-2 my-1 max-h-72 overflow-auto rounded-md border border-edge bg-bg p-3 text-[11px] leading-relaxed text-muted">
                      {JSON.stringify(record, null, 2)}
                    </pre>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {truncated && !loading && !loadError && (
        <div className="mt-2 flex items-center justify-between gap-2 text-xs text-faint">
          <p>Long day — more lines remain past what&apos;s shown.</p>
          <button
            type="button"
            onClick={() => void loadMore()}
            disabled={loadingMore}
            className="rounded-md border border-edge px-3 py-1.5 text-muted transition-colors hover:text-ink disabled:opacity-50"
          >
            {loadingMore ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}
