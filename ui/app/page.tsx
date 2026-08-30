import { getAccount } from "@/lib/alpaca";
import { recentSessions } from "@/lib/ledger";

export const dynamic = "force-dynamic";

/**
 * Pre-construction landing page.
 *
 * This page exists only until the UI manager builds the real interface.
 * It explains the arrangement to the owner and surfaces whatever basics
 * are already reachable — account equity and the most recent trading
 * session — each rendered only if its source is available. The UI manager
 * replaces this page as its first act of construction.
 */

function formatUsd(value: string | number): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function formatWhen(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default async function HomePage() {
  const account = await getAccount();
  const [lastSession] = recentSessions(1);

  return (
    <div className="flex flex-col items-center pt-16 text-center">
      <p className="font-mono text-xs uppercase tracking-[0.3em] text-faint">
        alpaca-mind
      </p>
      <h1 className="mt-4 text-3xl font-semibold tracking-tight text-ink">
        The mind is awakening
      </h1>
      <p className="mt-4 max-w-xl leading-relaxed text-muted">
        An autonomous agent is preparing to trade on this account. A second
        agent — the UI manager — will construct this interface after the
        first trading sessions, shaping it around what the trader actually
        does and learns. Until then, this page shows the essentials.
      </p>

      <div className="mt-12 grid w-full max-w-2xl gap-4 sm:grid-cols-2">
        <section className="rounded-lg border border-edge bg-surface p-6 text-left">
          <h2 className="text-xs font-medium uppercase tracking-wider text-faint">
            Account equity
          </h2>
          {account ? (
            <>
              <p className="mt-2 font-mono text-2xl text-ink">
                {formatUsd(account.equity)}
              </p>
              <p className="mt-1 text-sm text-muted">
                Cash {formatUsd(account.cash)} · Buying power{" "}
                {formatUsd(account.buying_power)}
              </p>
            </>
          ) : (
            <p className="mt-2 text-sm text-faint">
              Not yet reachable — account credentials may not be configured.
            </p>
          )}
        </section>

        <section className="rounded-lg border border-edge bg-surface p-6 text-left">
          <h2 className="text-xs font-medium uppercase tracking-wider text-faint">
            Last trading session
          </h2>
          {lastSession ? (
            <>
              <p className="mt-2 font-mono text-sm text-ink">
                {lastSession.run_type} · {formatWhen(lastSession.ts_start)}
              </p>
              {lastSession.summary ? (
                <p className="mt-2 line-clamp-4 text-sm leading-relaxed text-muted">
                  {lastSession.summary}
                </p>
              ) : (
                <p className="mt-2 text-sm text-faint">No summary recorded.</p>
              )}
            </>
          ) : (
            <p className="mt-2 text-sm text-faint">
              No sessions yet — the trader has not run.
            </p>
          )}
        </section>
      </div>

      <p className="mt-12 text-sm text-faint">
        Have a request for the interface? Leave it in the{" "}
        <a href="/inbox" className="text-accent hover:underline">
          inbox
        </a>
        .
      </p>
    </div>
  );
}
