# Style — the default design language

*The intended look and feel of this interface. The UI manager reads
this before building; the deploying AI edits this file (plus the
variables in `app/globals.css`) when the owner asks for a different
aesthetic at setup. The owner can change any of it later through the
inbox.*

## The feel, in one line

A premium, quiet, professional financial product: dark, spacious,
confident — the kind of interface that earns trust by restraint, not
by motion.

## Principles

- **Restraint is the premium.** Generous whitespace, a calm hierarchy,
  few colors each meaning one thing. No decorative animation, no
  gradients for their own sake, no dashboard-widget clutter. If an
  element doesn't inform, it doesn't ship.
- **One accent.** The warm gold (`accent`) marks interaction and
  emphasis — links, active nav, the occasional highlighted figure. It
  is a signature, not a paint bucket: a page should carry a little of
  it, never a lot.
- **Color is meaning.** `gain` green and `loss` red belong to financial
  values only. `warn` orange belongs to caution states only. Text
  lives on the `ink`/`muted`/`faint` ladder — three levels are enough
  for almost any surface.
- **Type does the design.** Clean geometric sans for prose and labels;
  mono for numbers, timestamps, and symbols so figures align and read
  as data. Size and weight changes are the main visual tool — use few
  steps, consistently.
- **Cards, softly.** Rounded corners (`rounded-lg`), hairline `edge`
  borders, `surface` on `bg` — depth from layering, not shadows.
- **Dark by default.** The shipped theme is dark and low-glare. A
  light theme is a legitimate owner request, built by re-deriving the
  same tokens — never by sprinkling conditional colors through
  components.

## Charts and illustration

Charts are where this interface earns "beautiful" — spend the craft
there. Install a proper charting library when a view deserves one
(any well-maintained npm package is allowed — see UI_GUIDE's
dependency note); hand-authored SVG is equally first-class for
sparklines, diagrams, and illustrations, and often crisper. Either
way: theme every chart through the CSS variables (no library default
palettes), label axes and units, mark data age where values can be
stale, and let gain/loss coloring agree with the rest of the app.
An equity curve, a P&L distribution, a schedule timeline — each should
look like it was drawn for THIS interface.

## Mechanics

All tokens live in `app/globals.css` as CSS variables, mapped to
semantic Tailwind names in `tailwind.config.ts` (`bg-surface`,
`text-muted`, `border-edge`, `text-accent`, ...). Restyle by editing
the variables — components reference only the semantic names, so the
whole interface re-themes from one file. Fonts are self-contained
system stacks; no external font loading, CDNs, or third-party scripts.
