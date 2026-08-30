"""Alpaca venue adapter — options-first, equities-capable.

Raw REST against api.alpaca.markets / data.alpaca.markets by design:
the endpoints this engine needs are simple, stable JSON calls, and a
dependency-free adapter keeps the deployment light and version-stable.

The engine talks to this adapter for TRUTH (sentinel polling, ledger
reconciliation, risk-relevant reads) and for order EXECUTION via the
trade tool. The agent's exploratory market access additionally flows
through Alpaca's MCP server mounted in its sessions — two surfaces,
one venue.

Env:
  ALPACA_API_KEY / ALPACA_SECRET_KEY
  ALPACA_PAPER          "true" (default) -> paper-api host, else live
  ALPACA_OPTIONS_FEED   "indicative" (default; free) or "opra"
                        (requires a market-data subscription)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from jsonlog import get_logger

DATA_BASE = "https://data.alpaca.markets"


class VenueError(RuntimeError):
    """A venue call failed; the body is preserved so the caller (and the
    agent reading the tool output) sees the venue's own reason."""


class Venue:
    name = "alpaca"

    def __init__(self):
        self.key = os.environ["ALPACA_API_KEY"]
        self.secret = os.environ["ALPACA_SECRET_KEY"]
        self.paper = os.environ.get("ALPACA_PAPER", "true").lower() != "false"
        self.api_base = ("https://paper-api.alpaca.markets" if self.paper
                         else "https://api.alpaca.markets")
        # Unset by default: omitting the feed parameter lets the venue
        # serve the account's entitled options feed, which includes
        # greeks — explicitly forcing the indicative feed has been
        # observed to return null greeks the entitled default provides.
        # Set ALPACA_OPTIONS_FEED to pin a specific feed deliberately.
        self.options_feed = os.environ.get("ALPACA_OPTIONS_FEED") or None
        # Constructed here, not at import: the entry point sets JSONLOG_DIR
        # from its config after imports resolve, and the logger reads the
        # environment when it is created.
        self.log = get_logger("venue")

    # -- HTTP -----------------------------------------------------------

    def _request(self, method: str, base: str, path: str,
                 params: dict | None = None, body: dict | None = None) -> dict:
        url = base + path
        # The query string carries symbols and filters, never credentials,
        # so it is safe in logs; headers are never logged.
        logged_path = path
        if params:
            query = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None})
            url += "?" + query
            logged_path = path + "?" + query
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "APCA-API-KEY-ID": self.key,
            "APCA-API-SECRET-KEY": self.secret,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                text = resp.read().decode()
                self.log.debug("venue_request", method=method,
                               path=logged_path, status=resp.status,
                               dur_ms=round((time.monotonic() - started) * 1000),
                               resp_bytes=len(text))
                return json.loads(text) if text.strip() else {}
        except urllib.error.HTTPError as e:
            body_text = e.read().decode()
            self.log.error("venue_request_failed", method=method,
                           path=logged_path, status=e.code,
                           dur_ms=round((time.monotonic() - started) * 1000),
                           body=body_text[:300], exc=e)
            raise VenueError(
                f"{method} {path} -> {e.code}: "
                f"{body_text[:500]}") from e
        except Exception as e:
            self.log.error("venue_request_failed", method=method,
                           path=logged_path,
                           dur_ms=round((time.monotonic() - started) * 1000),
                           exc=e)
            raise

    def _get(self, base, path, params=None):
        return self._request("GET", base, path, params)

    # -- account / positions --------------------------------------------

    def account(self) -> dict:
        a = self._get(self.api_base, "/v2/account")
        return {
            "equity": float(a["equity"]),
            "cash": float(a["cash"]),
            "positions_value": float(a["equity"]) - float(a["cash"]),
            "buying_power": float(a.get("buying_power") or 0),
            "options_approved_level": a.get("options_approved_level"),
            "options_buying_power": float(a.get("options_buying_power") or 0),
            "raw": a,
        }

    def positions(self) -> list[dict]:
        rows = self._get(self.api_base, "/v2/positions")
        out = []
        for p in rows:
            qty = float(p["qty"])
            out.append({
                "symbol": p["symbol"],
                "asset_class": p.get("asset_class"),
                "qty": qty,
                "side": "long" if qty > 0 else "short",
                "entry_price": float(p["avg_entry_price"]),
                "multiplier": float(p.get("multiplier") or 1),
                "market_value": float(p.get("market_value") or 0),
                "unrealized_pnl": float(p.get("unrealized_pl") or 0),
                "unrealized_pnl_pct": float(p.get("unrealized_plpc") or 0) * 100,
                "raw": p,
            })
        return out

    def is_market_open(self) -> bool:
        return bool(self._get(self.api_base, "/v2/clock").get("is_open"))

    def clock(self) -> dict:
        return self._get(self.api_base, "/v2/clock")

    # -- stock market data ----------------------------------------------

    def quotes(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        d = self._get(DATA_BASE, "/v2/stocks/quotes/latest",
                      {"symbols": ",".join(symbols)})
        trades = {}
        try:
            t = self._get(DATA_BASE, "/v2/stocks/trades/latest",
                          {"symbols": ",".join(symbols)})
            trades = {s: {"price": float(v["p"]), "ts": v.get("t")}
                      for s, v in t.get("trades", {}).items() if v.get("p")}
        except VenueError:
            pass
        out = []
        for s, q in d.get("quotes", {}).items():
            bid, ask = float(q["bp"]), float(q["ap"])
            # last = real last trade; midpoint ONLY when both sides are
            # live — a midpoint against a zero side halves the price.
            t = trades.get(s)
            if t:
                last = t["price"]
            elif bid > 0 and ask > 0:
                last = (bid + ask) / 2
            else:
                last = None
            out.append({"symbol": s, "bid": bid, "ask": ask, "last": last,
                        "ts": q.get("t"), "trade_ts": t["ts"] if t else None})
        return out

    def quote(self, symbol: str) -> dict:
        qs = self.quotes([symbol])
        return qs[0] if qs else {"symbol": symbol, "bid": 0, "ask": 0,
                                 "last": None, "ts": None}

    def snapshots(self, symbols: list[str]) -> dict:
        """Batched stock snapshots (dailyBar + prevDailyBar per symbol)."""
        out: dict = {}
        for i in range(0, len(symbols), 400):
            try:
                d = self._get(DATA_BASE, "/v2/stocks/snapshots",
                              {"symbols": ",".join(symbols[i:i + 400])})
            except VenueError:
                continue
            out.update(d.get("snapshots", d) if isinstance(d, dict) else {})
        return out

    def movers(self, top: int = 25) -> dict:
        d = self._get(DATA_BASE, "/v1beta1/screener/stocks/movers",
                      {"top": top})
        fmt = lambda rows: [
            {"symbol": r["symbol"], "pct": float(r["percent_change"]),
             "change": float(r["change"]), "price": float(r["price"])}
            for r in rows]
        return {"gainers": fmt(d.get("gainers", [])),
                "losers": fmt(d.get("losers", []))}

    def news(self, symbols: list[str] | None = None, since_hours: float = 24,
             limit: int = 30) -> list[dict]:
        """Timestamped headlines — catalyst detection for entries and for
        'was this move detectable at the time?' reviews alike."""
        from datetime import datetime, timedelta, timezone
        start = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        params = {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "limit": min(limit, 50), "sort": "desc"}
        if symbols:
            params["symbols"] = ",".join(symbols)
        d = self._get(DATA_BASE, "/v1beta1/news", params)
        return [{
            "at": n.get("created_at"),
            "headline": n.get("headline"),
            "symbols": n.get("symbols"),
            "source": n.get("source"),
            "summary": (n.get("summary") or "")[:300],
            "url": n.get("url"),
        } for n in d.get("news", [])]

    # -- options market data --------------------------------------------

    def option_contracts(self, underlying: str,
                         expiration_gte: str | None = None,
                         expiration_lte: str | None = None,
                         strike_gte: float | None = None,
                         strike_lte: float | None = None,
                         contract_type: str | None = None,
                         limit: int = 500) -> list[dict]:
        """Tradable option contracts (metadata: strike, expiry, OI)."""
        rows: list[dict] = []
        params = {"underlying_symbols": underlying,
                  "expiration_date_gte": expiration_gte,
                  "expiration_date_lte": expiration_lte,
                  "strike_price_gte": strike_gte,
                  "strike_price_lte": strike_lte,
                  "type": contract_type,
                  "limit": min(limit, 10000)}
        d = self._get(self.api_base, "/v2/options/contracts", params)
        for c in d.get("option_contracts", []):
            rows.append({
                "symbol": c["symbol"],
                "underlying": c.get("underlying_symbol"),
                "type": c.get("type"),
                "strike": float(c.get("strike_price") or 0),
                "expiration": c.get("expiration_date"),
                "multiplier": float(c.get("multiplier") or 100),
                "open_interest": c.get("open_interest"),
                "close_price": c.get("close_price"),
                "tradable": c.get("tradable"),
            })
        return rows

    def option_chain(self, underlying: str,
                     expiration_gte: str | None = None,
                     expiration_lte: str | None = None,
                     strike_gte: float | None = None,
                     strike_lte: float | None = None,
                     contract_type: str | None = None) -> list[dict]:
        """Chain snapshots with quotes and greeks for an underlying,
        on the account's entitled feed unless ALPACA_OPTIONS_FEED pins
        one."""
        out: list[dict] = []
        params = {"feed": self.options_feed,
                  "type": contract_type,
                  "strike_price_gte": strike_gte,
                  "strike_price_lte": strike_lte,
                  "expiration_date_gte": expiration_gte,
                  "expiration_date_lte": expiration_lte,
                  "limit": 250}
        page = None
        for _ in range(8):  # pagination bound; a chain slice never needs more
            if page:
                params["page_token"] = page
            d = self._get(DATA_BASE,
                          f"/v1beta1/options/snapshots/{underlying}", params)
            for sym, s in (d.get("snapshots") or {}).items():
                q = s.get("latestQuote") or {}
                g = s.get("greeks") or {}
                t = s.get("latestTrade") or {}
                out.append({
                    "symbol": sym,
                    "bid": float(q.get("bp") or 0),
                    "ask": float(q.get("ap") or 0),
                    "last": float(t.get("p") or 0) or None,
                    "iv": s.get("impliedVolatility"),
                    "delta": g.get("delta"), "gamma": g.get("gamma"),
                    "theta": g.get("theta"), "vega": g.get("vega"),
                })
            page = d.get("next_page_token")
            if not page:
                break
        return out

    def option_quotes(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        d = self._get(DATA_BASE, "/v1beta1/options/quotes/latest",
                      {"symbols": ",".join(symbols),
                       "feed": self.options_feed})
        out = []
        for s, q in (d.get("quotes") or {}).items():
            out.append({"symbol": s, "bid": float(q.get("bp") or 0),
                        "ask": float(q.get("ap") or 0), "ts": q.get("t")})
        return out

    # -- orders ----------------------------------------------------------

    @staticmethod
    def _order_dict(o: dict) -> dict:
        legs = o.get("legs") or None
        return {
            "venue_order_id": str(o.get("id")),
            "status": str(o.get("status", "")).lower(),
            "filled_qty": float(o.get("filled_qty") or 0),
            "filled_avg_price": (float(o["filled_avg_price"])
                                 if o.get("filled_avg_price") else None),
            "fees": 0.0,   # commission-free venue; regulatory fees are
                           # cents per contract and excluded from P&L here
            "legs": legs,
            "raw": o,
        }

    def place_order(self, symbol: str, side: str, order_type: str = "market",
                    qty: Optional[float] = None,
                    notional: Optional[float] = None,
                    limit_price: Optional[float] = None,
                    stop_price: Optional[float] = None,
                    time_in_force: str = "day") -> dict:
        """Single-leg order — stock or option (OCC symbol). Options
        require whole-contract qty and day tif at this venue."""
        body: dict = {"symbol": symbol, "side": side, "type": order_type,
                      "time_in_force": time_in_force}
        if qty is not None:
            body["qty"] = str(qty)
        elif notional is not None:
            body["notional"] = str(round(notional, 2))
        if limit_price is not None:
            body["limit_price"] = str(limit_price)
        if stop_price is not None:
            body["stop_price"] = str(stop_price)
        return self._order_dict(
            self._request("POST", self.api_base, "/v2/orders", body=body))

    def place_mleg_order(self, legs: list[dict], qty: int,
                         order_type: str = "limit",
                         limit_price: Optional[float] = None,
                         time_in_force: str = "day") -> dict:
        """Multi-leg options order (spreads, condors, …). Each leg:
        {symbol, ratio_qty, side: buy|sell, position_intent:
        buy_to_open|buy_to_close|sell_to_open|sell_to_close}.
        limit_price sign follows the venue's convention: positive = net
        debit you pay, negative = net credit you receive."""
        body: dict = {"order_class": "mleg", "qty": str(qty),
                      "type": order_type, "time_in_force": time_in_force,
                      "legs": [{"symbol": l["symbol"],
                                "ratio_qty": str(l.get("ratio_qty", 1)),
                                "side": l["side"],
                                "position_intent": l["position_intent"]}
                               for l in legs]}
        if limit_price is not None:
            body["limit_price"] = str(limit_price)
        return self._order_dict(
            self._request("POST", self.api_base, "/v2/orders", body=body))

    def get_order(self, venue_order_id: str) -> dict:
        return self._order_dict(
            self._get(self.api_base, f"/v2/orders/{venue_order_id}"))

    def cancel_order(self, venue_order_id: str) -> dict:
        self._request("DELETE", self.api_base,
                      f"/v2/orders/{venue_order_id}")
        return {"venue_order_id": venue_order_id,
                "status": "cancel_requested"}

    def open_orders(self) -> list[dict]:
        rows = self._get(self.api_base, "/v2/orders",
                         {"status": "open", "limit": 500})
        return [self._order_dict(o) for o in rows]

    def close_position(self, symbol: str,
                       qty: Optional[float] = None) -> dict:
        params = {"qty": qty} if qty else None
        return self._order_dict(self._request(
            "DELETE", self.api_base,
            f"/v2/positions/{urllib.parse.quote(symbol)}", params=params))
