/**
 * Thin, read-only Alpaca REST helpers.
 *
 * The UI layer reads account state to display it; it never places, alters,
 * or cancels orders. Order placement belongs to the trading agent alone —
 * this module deliberately exposes only GET endpoints and should stay that
 * way.
 *
 * Credentials come from the environment:
 *   ALPACA_API_KEY, ALPACA_SECRET_KEY — the account keys
 *   ALPACA_PAPER — "true" (default) targets the paper-trading API;
 *                  anything else targets the live API.
 *
 * Every helper returns null on missing credentials or request failure so
 * pages can render without account data rather than erroring.
 */

const PAPER_BASE = "https://paper-api.alpaca.markets";
const LIVE_BASE = "https://api.alpaca.markets";

export interface AlpacaAccount {
  id: string;
  status: string;
  currency: string;
  equity: string;
  last_equity: string;
  cash: string;
  buying_power: string;
  portfolio_value: string;
  daytrade_count: number;
  pattern_day_trader: boolean;
}

export interface AlpacaPosition {
  symbol: string;
  qty: string;
  side: string;
  avg_entry_price: string;
  current_price: string;
  market_value: string;
  cost_basis: string;
  unrealized_pl: string;
  unrealized_plpc: string;
  change_today: string;
}

function baseUrl(): string {
  const paper = (process.env.ALPACA_PAPER ?? "true").toLowerCase();
  return paper === "true" ? PAPER_BASE : LIVE_BASE;
}

/** Perform an authenticated GET against the Alpaca trading API. */
async function alpacaGet<T>(endpoint: string): Promise<T | null> {
  const key = process.env.ALPACA_API_KEY;
  const secret = process.env.ALPACA_SECRET_KEY;
  if (!key || !secret) {
    return null;
  }

  try {
    const response = await fetch(`${baseUrl()}${endpoint}`, {
      headers: {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        Accept: "application/json",
      },
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

/** Current account state (equity, cash, buying power), or null. */
export async function getAccount(): Promise<AlpacaAccount | null> {
  return alpacaGet<AlpacaAccount>("/v2/account");
}

/** All open positions, or null when the account is unreachable. */
export async function getPositions(): Promise<AlpacaPosition[] | null> {
  return alpacaGet<AlpacaPosition[]>("/v2/positions");
}
