import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "alpaca-mind",
  description: "Autonomous trading agent — owner interface",
};

/**
 * Top navigation. The UI manager adds nav links here as it creates pages:
 * append `{ href, label }` entries to this array and the header renders
 * them in order. Keep labels short (one or two words).
 */
const NAV_LINKS: { href: string; label: string }[] = [
  { href: "/", label: "Home" },
  { href: "/inbox", label: "Inbox" },
];

/**
 * Application shell: a fixed header with brand and navigation, and a
 * centered content column. Pages render inside the <main> slot; the UI
 * manager builds every page within this frame so the interface keeps a
 * single consistent chrome.
 */
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="sticky top-0 z-10 border-b border-edge bg-bg/90 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-5xl items-center gap-8 px-6">
            <Link
              href="/"
              className="font-mono text-sm font-semibold tracking-wide text-ink"
            >
              alpaca<span className="text-accent">-</span>mind
            </Link>
            <nav className="flex items-center gap-5">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="text-sm text-muted transition-colors hover:text-ink"
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
      </body>
    </html>
  );
}
