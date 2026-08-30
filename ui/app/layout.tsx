import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "alpaca-mind",
  description: "Autonomous trading agent — owner interface",
};

/**
 * Navigation. The UI manager adds entries here as it creates pages; the
 * shell renders them as a left sidebar on desktop and a top bar on small
 * screens. Keep labels short (one or two words). Reshaping the chrome
 * itself (a top nav, grouped sections, ...) is allowed — the one rule is
 * that this array stays the single source of navigation.
 */
const NAV_LINKS: { href: string; label: string }[] = [
  { href: "/", label: "Dashboard" },
  { href: "/logs", label: "Logs" },
  { href: "/inbox", label: "Inbox" },
];

function Brand() {
  return (
    <Link
      href="/"
      className="font-mono text-sm font-semibold tracking-wide text-ink"
    >
      alpaca<span className="text-accent">-</span>mind
    </Link>
  );
}

/**
 * Application shell: left sidebar (desktop) / top bar (mobile) plus the
 * content column. Pages render inside the <main> slot; every page lives
 * within this frame so the interface keeps a single consistent chrome.
 */
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="sticky top-0 z-10 border-b border-edge bg-bg/90 backdrop-blur md:hidden">
          <div className="flex h-14 items-center gap-6 overflow-x-auto px-5">
            <Brand />
            <nav className="flex items-center gap-5">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="whitespace-nowrap text-sm text-muted transition-colors hover:text-ink"
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>

        <div className="mx-auto flex min-h-screen max-w-6xl">
          <aside className="hidden w-52 shrink-0 border-r border-edge md:block">
            <div className="sticky top-0 flex h-screen flex-col gap-8 px-5 py-8">
              <Brand />
              <nav className="flex flex-col gap-1">
                {NAV_LINKS.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="rounded-md px-3 py-2 text-sm text-muted transition-colors hover:bg-raised hover:text-ink"
                  >
                    {link.label}
                  </Link>
                ))}
              </nav>
            </div>
          </aside>
          <main className="min-w-0 flex-1 px-6 py-10">{children}</main>
        </div>
      </body>
    </html>
  );
}
