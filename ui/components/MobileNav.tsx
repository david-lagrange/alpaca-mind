"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

/**
 * Mobile navigation drawer — shipped as a GIFT, not a mandate.
 *
 * Its styling and theming are entirely yours: restyle it, rebuild it,
 * or replace the whole chrome with something that matches the owner's
 * taste — this is just a working starting point you may use or discard.
 *
 * The only part worth preserving in whatever you build instead is the
 * BEHAVIOR, because these aren't style choices — they're what makes any
 * drawer trustworthy on a phone:
 *   - background scroll is locked while the menu is open
 *   - the menu closes on navigation, on backdrop tap, and on Escape
 *   - the trigger reports its state (aria-expanded)
 */

export type NavLink = { href: string; label: string };

export default function MobileNav({ links }: { links: NavLink[] }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        aria-expanded={open}
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((v) => !v)}
        className="ml-auto flex h-9 w-9 items-center justify-center rounded-md text-muted transition-colors hover:bg-raised hover:text-ink"
      >
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
          {open ? (
            <path
              d="M3 3l12 12M15 3L3 15"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          ) : (
            <path
              d="M2 4.5h14M2 9h14M2 13.5h14"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          )}
        </svg>
      </button>

      {open && (
        <div className="fixed inset-0 top-14 z-20">
          <div
            className="absolute inset-0 bg-bg/70 backdrop-blur-sm"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <nav className="relative max-h-full overflow-y-auto border-b border-edge bg-surface px-4 py-3 shadow-lg">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className="block rounded-md px-3 py-2.5 text-sm text-muted transition-colors hover:bg-raised hover:text-ink"
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      )}
    </>
  );
}
