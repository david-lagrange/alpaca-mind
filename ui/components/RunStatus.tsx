"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * The manager's run status and the "run now" button — shipped as a GIFT,
 * like the mobile drawer: restyle it, rebuild it, or fold it into a
 * larger panel. What is worth preserving in whatever replaces it is the
 * BEHAVIOR, because these are what make the button trustworthy:
 *   - pressing it gives feedback in place, without navigating away
 *   - "running" and its clock come from the manager's own newest session
 *     row (/api/inbox/status), so the clock counts from that pass's own
 *     start and a hung pass keeps counting rather than pretending to end
 *   - a finished pass shows its exit code; a non-zero one says so
 *   - the button disables itself while a request or a pass is in flight
 */

interface ManagerSession {
  id: string;
  run_type: string | null;
  ts_start: number;
  ts_end: number | null;
  exit_code: number | null;
  num_turns: number | null;
}

interface StatusPayload {
  now: number;
  requested_at: string | null;
  next_run_at: string | null;
  available: boolean;
  session: ManagerSession | null;
}

type Phase = "loading" | "idle" | "requested" | "running";

const FAST_POLL_MS = 5_000;
const SLOW_POLL_MS = 30_000;

function fmtDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m > 0) return `${m}m ${String(sec).padStart(2, "0")}s`;
  return `${sec}s`;
}

function fmtAgo(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86_400)}d ago`;
}

function phaseOf(status: StatusPayload | null): Phase {
  if (!status) return "loading";
  if (status.session && status.session.ts_end === null) return "running";
  if (status.requested_at) return "requested";
  return "idle";
}

export default function RunStatus({ unread }: { unread: number }) {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [posting, setPosting] = useState(false);
  // A local clock so the elapsed counter ticks between polls; the server
  // clock in each payload re-anchors it, so a skewed browser cannot drift it.
  const [skew, setSkew] = useState(0);
  const [, setTick] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/inbox/status", { cache: "no-store" });
      if (!response.ok) throw new Error(`status ${response.status}`);
      const payload = (await response.json()) as StatusPayload;
      setStatus(payload);
      setSkew(payload.now - Date.now() / 1000);
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loop = async () => {
      await refresh();
      if (cancelled) return;
      const busy = phaseOf(status) !== "idle";
      timer.current = setTimeout(loop, busy ? FAST_POLL_MS : SLOW_POLL_MS);
    };
    loop();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
    // The poll cadence follows the phase; re-arming on phase change is intended.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phaseOf(status)]);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const requestRun = async () => {
    setPosting(true);
    try {
      const response = await fetch("/api/run-now", {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`run-now ${response.status}`);
      setStatus((prev) =>
        prev
          ? { ...prev, requested_at: new Date().toISOString() }
          : prev
      );
      setError(null);
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setPosting(false);
    }
  };

  const phase = phaseOf(status);
  const nowSec = Date.now() / 1000 + skew;
  const session = status?.session ?? null;
  const busy = phase === "requested" || phase === "running" || posting;

  let dot = "bg-faint";
  let line: string;
  let detail: string | null = null;
  if (phase === "loading") {
    line = "Reading the manager's state…";
  } else if (phase === "running" && session) {
    dot = "bg-warn animate-pulse";
    line = `The UI manager is working — ${session.run_type ?? "pass"} · running for ${fmtDuration(nowSec - session.ts_start)}`;
  } else if (phase === "requested" && status) {
    dot = "bg-warn";
    const since = status.requested_at
      ? (Date.now() - new Date(status.requested_at).getTime()) / 1000
      : 0;
    line = `Asked. Waiting for the manager to pick the request up (${fmtDuration(since)}).`;
  } else if (session && session.ts_end !== null) {
    const ok = session.exit_code === 0;
    dot = ok ? "bg-gain" : "bg-warn";
    line = `Last pass finished ${fmtAgo(nowSec - session.ts_end)} after ${fmtDuration(session.ts_end - session.ts_start)}`;
    detail = ok
      ? `${session.run_type ?? "pass"} · exit 0${session.num_turns ? ` · ${session.num_turns} turns` : ""}`
      : `${session.run_type ?? "pass"} · exit ${session.exit_code ?? "?"} — the pass did not finish cleanly`;
  } else if (status && !status.available) {
    line = "The manager's own record is not readable here; the button still works.";
  } else {
    line = "No pass has run yet.";
  }

  return (
    <div className="mt-4 rounded-lg border border-edge bg-surface p-4">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-sm text-muted">
            <span
              aria-hidden="true"
              className={`inline-block h-2 w-2 shrink-0 rounded-full ${dot}`}
            />
            <span className="truncate">{line}</span>
          </p>
          {detail && (
            <p
              className={`mt-1 pl-4 font-mono text-xs ${session?.exit_code === 0 ? "text-faint" : "text-warn"}`}
            >
              {detail}
            </p>
          )}
          {unread > 0 && (
            <p className="mt-1 pl-4 text-xs text-faint">
              {unread} unread {unread === 1 ? "message" : "messages"} waiting.
            </p>
          )}
          {error && (
            <p className="mt-1 pl-4 font-mono text-xs text-warn">{error}</p>
          )}
        </div>
        <button
          type="button"
          onClick={requestRun}
          disabled={busy}
          aria-busy={busy}
          className="shrink-0 rounded-md border border-warn/50 px-4 py-1.5 text-sm font-medium text-warn transition-colors hover:bg-warn/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {phase === "running"
            ? "Running…"
            : phase === "requested"
              ? "Requested"
              : "Run UI manager now"}
        </button>
      </div>
    </div>
  );
}
