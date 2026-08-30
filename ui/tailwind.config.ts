import type { Config } from "tailwindcss";

/**
 * Tailwind is wired to the CSS variables defined in app/globals.css.
 * Use the semantic color names below (bg, surface, ink, accent, gain,
 * loss, ...) instead of raw hex values so the whole interface stays
 * consistent and can be re-themed by editing the variables in one place.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "rgb(var(--color-bg) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        raised: "rgb(var(--color-raised) / <alpha-value>)",
        edge: "rgb(var(--color-edge) / <alpha-value>)",
        ink: "rgb(var(--color-ink) / <alpha-value>)",
        muted: "rgb(var(--color-muted) / <alpha-value>)",
        faint: "rgb(var(--color-faint) / <alpha-value>)",
        accent: "rgb(var(--color-accent) / <alpha-value>)",
        gain: "rgb(var(--color-gain) / <alpha-value>)",
        loss: "rgb(var(--color-loss) / <alpha-value>)",
        warn: "rgb(var(--color-warn) / <alpha-value>)",
      },
      fontFamily: {
        sans: "var(--font-sans)",
        mono: "var(--font-mono)",
      },
    },
  },
  plugins: [],
};

export default config;
