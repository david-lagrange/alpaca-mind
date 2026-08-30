import { kvGet, listInbox, unreadInboxCount } from "@/lib/db";

export const dynamic = "force-dynamic";

/**
 * Owner → UI-manager inbox.
 *
 * This is how the owner steers what the interface shows — not how the
 * agent trades. Messages left here are read by the UI manager on its next
 * run; it builds or adjusts the interface to address them, then marks each
 * message read/addressed with a note explaining what it did.
 *
 * When unread messages are waiting, the owner can request an immediate
 * UI-manager run instead of waiting for the schedule; the request is a
 * file the manager's scheduler watches for (see /api/run-now).
 */

function formatIso(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function StatusBadge({
  label,
  tone,
}: {
  label: string;
  tone: "gain" | "warn" | "faint";
}) {
  const tones: Record<string, string> = {
    gain: "border-gain/40 text-gain",
    warn: "border-warn/40 text-warn",
    faint: "border-edge text-faint",
  };
  return (
    <span
      className={`rounded-full border px-2 py-0.5 font-mono text-[11px] ${tones[tone]}`}
    >
      {label}
    </span>
  );
}

export default function InboxPage() {
  const messages = listInbox();
  const unread = unreadInboxCount();
  const nextRunAt = kvGet("next_run_at");

  return (
    <div className="mx-auto max-w-2xl">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold tracking-tight text-ink">
          Inbox
        </h1>
        {nextRunAt && (
          <p className="text-sm text-faint">
            Next UI-manager run:{" "}
            <span className="font-mono text-muted">
              {formatIso(nextRunAt)}
            </span>
          </p>
        )}
      </div>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Tell the UI manager what you want to see. It reads these messages
        before each construction run, builds the interface to address them,
        and leaves a note on each one describing what changed. This channel
        steers visibility only — it does not direct trading.
      </p>

      <form
        method="post"
        action="/api/inbox"
        className="mt-6 rounded-lg border border-edge bg-surface p-4"
      >
        <label
          htmlFor="body"
          className="block text-xs font-medium uppercase tracking-wider text-faint"
        >
          New message
        </label>
        <textarea
          id="body"
          name="body"
          required
          minLength={1}
          maxLength={4000}
          rows={3}
          placeholder="e.g. Show me each trade's thesis next to its outcome."
          className="mt-2 w-full resize-y rounded-md border border-edge bg-raised p-3 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none"
        />
        <div className="mt-3 flex items-center justify-between">
          <p className="text-xs text-faint">
            Read on the UI manager&apos;s next run.
          </p>
          <button
            type="submit"
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-bg transition-opacity hover:opacity-90"
          >
            Send
          </button>
        </div>
      </form>

      {unread > 0 && (
        <form
          method="post"
          action="/api/run-now"
          className="mt-4 flex items-center justify-between rounded-lg border border-warn/30 bg-surface p-4"
        >
          <p className="text-sm text-muted">
            {unread} unread {unread === 1 ? "message" : "messages"} waiting.
          </p>
          <button
            type="submit"
            className="rounded-md border border-warn/50 px-4 py-1.5 text-sm font-medium text-warn transition-colors hover:bg-warn/10"
          >
            Run UI manager now
          </button>
        </form>
      )}

      <ul className="mt-8 space-y-3">
        {messages.length === 0 && (
          <li className="rounded-lg border border-dashed border-edge p-6 text-center text-sm text-faint">
            No messages yet.
          </li>
        )}
        {messages.map((message) => (
          <li
            key={message.id}
            className="rounded-lg border border-edge bg-surface p-4"
          >
            <div className="flex items-center justify-between gap-3">
              <time className="font-mono text-xs text-faint">
                {formatIso(message.created_at)}
              </time>
              <div className="flex gap-1.5">
                {message.addressed ? (
                  <StatusBadge label="addressed" tone="gain" />
                ) : message.read ? (
                  <StatusBadge label="read" tone="warn" />
                ) : (
                  <StatusBadge label="unread" tone="faint" />
                )}
              </div>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink">
              {message.body}
            </p>
            {message.addressed_note && (
              <p className="mt-3 border-l-2 border-gain/40 pl-3 text-sm leading-relaxed text-muted">
                {message.addressed_note}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
