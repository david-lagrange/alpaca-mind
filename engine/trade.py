#!/usr/bin/env python3
"""trade — the agent's execution path to the market.

Every order is written to the ledger automatically at execution time, so
the ledger cannot drift from reality by forgetfulness. This tool
enforces exactly TWO bounds, and both are machine-failure protections,
never judgment constraints:

  * HALT — the owner's kill switch (a file in state/). The owner's
    property right over their own deployment, not distrust of the agent.
  * orders-per-hour — a runaway-code bound. It exists to stop a crash
    loop from spamming the venue; a mind making decisions never hits it.

Everything else — what to trade, how to size, when to exit, what risk
doctrine to hold — belongs to the agent. Strategy is not enforced here
because strategy is the agent's own evolving judgment.

Usage (all output is JSON on stdout):
  trade account | positions | orders | movers | status
  trade quote SYMBOL [SYMBOL ...]          # stocks
  trade oquote OCC_SYMBOL [...]            # option contracts
  trade chain --underlying SPY [--type call|put] [--exp-gte D] [--exp-lte D]
              [--strike-gte X] [--strike-lte X]      # quotes + greeks
  trade contracts --underlying SPY [...]   # tradable contracts metadata
  trade open  --symbol S --side long|short (--qty N | --notional USD)
              [--type market|limit|stop|stop_limit] [--limit-price X]
              [--stop-price X] [--tif day|gtc] --thesis "why"
  trade spread --legs "SYM:sell_to_open:1,SYM:buy_to_open:1" --qty N
              [--limit-price X] --thesis "why"       # multi-leg options
  trade close (--symbol S | --trade-id N) [--reason "..."]
              [--type market|stop|stop_limit] [--stop-price X] [--limit-price X]
  trade cancel --order-id VENUE_ORDER_ID
  trade reconcile [--heal]
  trade recent [--days 7]
  trade news [--symbols A,B] [--hours 24] [--limit 30]
  trade events [--minutes 15] [--kind a,b] [--limit 50]
  trade reviewed TRADE_ID

Environment:
  MIND_CONFIG      path to instance yaml (set by the service unit)
  MIND_SESSION_ID  current session id for ledger attribution
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import yaml

ENGINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE_DIR))

from jsonlog import get_logger                   # noqa: E402
from ledger import Ledger, OPEN_ORDER_STATUSES  # noqa: E402
from venue import Venue                          # noqa: E402

# Rebound in main() once config supplies JSONLOG_DIR; until then records
# reach stderr only.
log = get_logger("trade")

OCC_RE = re.compile(r"^[A-Z.]{1,6}\d{6}[CP]\d{8}$")


def is_option(symbol: str) -> bool:
    return bool(OCC_RE.match(symbol))


def load_config() -> dict:
    cfg_path = os.environ.get("MIND_CONFIG")
    if not cfg_path:
        fail("MIND_CONFIG env var not set")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def out(data) -> None:
    try:
        print(json.dumps(data, indent=2, default=str))
    except BrokenPipeError:
        # The reader closed the pipe (`trade chain | head`) after taking
        # what it needed. The unix convention is a quiet exit — not a
        # stack trace and a false error event over a satisfied consumer.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)


def fail(msg: str, **extra) -> None:
    print(json.dumps({"ok": False, "error": msg, **extra}, default=str))
    sys.exit(1)


def day_start_ts() -> float:
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


# ---------------------------------------------------------------------------
# The two bounds
# ---------------------------------------------------------------------------

def check_bounds(cfg: dict, ledger: Ledger) -> list[str]:
    """Empty list == the order may proceed. Only machine-failure bounds
    live here — see the module docstring for why there is nothing else."""
    violations = []
    halt_file = Path(cfg["paths"]["state"]) / "HALT"
    if halt_file.exists():
        violations.append(
            f"HALT file present ({halt_file}) — the owner has disabled "
            "trading")
    cap = int((cfg.get("bounds") or {}).get("max_orders_per_hour", 60))
    if ledger.orders_in_last(3600) >= cap:
        violations.append(
            f"max_orders_per_hour ({cap}) reached — this is a runaway-code "
            "bound; if you are hitting it with deliberate decisions, note "
            "it for the owner")
    return violations


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _ref_price(venue: Venue, symbol: str, limit_price) -> float | None:
    if limit_price:
        return limit_price
    if is_option(symbol):
        qs = venue.option_quotes([symbol])
        if qs:
            b, a = qs[0]["bid"], qs[0]["ask"]
            return (b + a) / 2 if b and a else (a or b or None)
        return None
    q = venue.quote(symbol)
    return q.get("last") or q.get("ask") or q.get("bid")


def cmd_open(args, cfg, ledger, venue) -> None:
    if not args.thesis or len(args.thesis.strip()) < 20:
        fail("--thesis is required (>=20 chars): every trade states why "
             "it exists")
    option = is_option(args.symbol)
    mult = 100 if option else 1
    ref = _ref_price(venue, args.symbol, args.limit_price)
    if not ref:
        fail(f"no price available for {args.symbol}")
    if args.qty is not None:
        qty = args.qty
        notional = qty * ref * mult
    else:
        notional = args.notional
        qty = max(1, int(notional / (ref * mult))) if option \
            else notional / ref

    violations = check_bounds(cfg, ledger)
    if violations:
        log.warn("order_blocked", symbol=args.symbol, violations=violations)
        ledger.record_event("trade_tool", "order_blocked",
                            {"symbol": args.symbol,
                             "violations": violations})
        fail("order blocked", violations=violations)

    order_side = "buy" if args.side == "long" else "sell"
    session_id = os.environ.get("MIND_SESSION_ID")

    # ATOMICITY: record intent BEFORE the venue sees the order. A crash
    # after this point leaves a `pending` row to reconcile — never a
    # phantom fill the ledger knows nothing about.
    order_id = ledger.record_order(
        venue=cfg["venue"], venue_order_id=None,
        symbol=args.symbol, side=order_side, order_type=args.type,
        qty=qty, notional=notional, limit_price=args.limit_price,
        stop_price=args.stop_price, status="pending",
        session_id=session_id, thesis=args.thesis)
    log.info("order_intent_recorded", order_id=order_id, symbol=args.symbol,
             side=order_side, order_type=args.type, qty=qty,
             notional=notional, limit_price=args.limit_price,
             stop_price=args.stop_price)
    try:
        result = venue.place_order(
            args.symbol, order_side, args.type,
            qty=qty if (option or args.qty is not None) else None,
            notional=None if (option or args.qty is not None) else notional,
            limit_price=args.limit_price, stop_price=args.stop_price,
            time_in_force=args.tif)
    except Exception as e:
        log.error("order_place_failed", exc=e, order_id=order_id,
                  symbol=args.symbol, side=order_side, order_type=args.type)
        ledger.update_order(order_id, status="error")
        fail(f"venue rejected/errored before fill: {type(e).__name__}: {e}")

    log.info("order_placed", order_id=order_id,
             venue_order_id=result["venue_order_id"], symbol=args.symbol,
             side=order_side, order_type=args.type, qty=qty,
             limit_price=args.limit_price, status=result["status"],
             filled_qty=result["filled_qty"])

    trade_id = None
    try:
        ledger.update_order(
            order_id, venue_order_id=result["venue_order_id"],
            status=result["status"], filled_qty=result["filled_qty"],
            filled_avg_price=result["filled_avg_price"], fees=result["fees"])
        # A trade exists when a FILL exists — not when an order is
        # accepted. Resting orders are watched by the sentinel, which
        # adopts the fill into the ledger and wakes the agent.
        if result["status"] == "filled" or (result["filled_qty"] or 0) > 0:
            trade_id = ledger.open_trade(
                venue=cfg["venue"], symbol=args.symbol, side=args.side,
                qty=result["filled_qty"] or qty,
                entry_price=result["filled_avg_price"] or ref,
                fees=result["fees"], thesis=args.thesis,
                session_id_open=session_id,
                meta={"multiplier": mult} if option else None)
            ledger.update_order(order_id, trade_id=trade_id)
    except Exception as e:
        # LAST RESORT: the venue may hold a live fill the DB could not
        # record. Persist the venue response somewhere that cannot fail
        # with the DB, then say so loudly.
        dump = Path(cfg["paths"]["state"]) / "unrecorded_fills.jsonl"
        with open(dump, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "symbol": args.symbol,
                                "side": args.side, "thesis": args.thesis,
                                "error": repr(e), "venue_result": result},
                               default=str) + "\n")
        log.error("unrecorded_fill", exc=e, order_id=order_id,
                  venue_order_id=result.get("venue_order_id"),
                  symbol=args.symbol, side=args.side,
                  status=result.get("status"),
                  filled_qty=result.get("filled_qty"),
                  filled_avg_price=result.get("filled_avg_price"),
                  dump=str(dump))
        ledger.record_event("trade_tool", "unrecorded_fill",
                            {"symbol": args.symbol, "dump": str(dump)})
        fail("ORDER PLACED AT VENUE but ledger write failed — venue result "
             f"saved to {dump}; run `trade reconcile`", venue_result=result)

    resting = (trade_id is None
               and result["status"] not in ("rejected", "canceled"))
    warnings = []
    if resting:
        warnings.append(
            "RESTING ORDER — no fill yet, so no ledger trade exists. The "
            "sentinel watches it: on fill it adopts the trade into the "
            "ledger and WAKES you. Do NOT wait for the fill in this "
            "session (background tasks die with the session) — arm any "
            "protection you want in triggers.json, then close the session "
            "properly.")
    out({"ok": result["status"] not in ("rejected",),
         "order": result | {"raw": "(stored in ledger)"},
         "trade_id": trade_id,
         "multiplier": mult,
         "resting": resting,
         "warnings": warnings})


def _parse_legs(spec: str) -> list[dict]:
    """--legs "OCC:sell_to_open:1,OCC:buy_to_open:1" -> leg dicts. The
    ratio defaults to 1; intent implies the side."""
    intents = {"buy_to_open": "buy", "buy_to_close": "buy",
               "sell_to_open": "sell", "sell_to_close": "sell"}
    legs = []
    for part in spec.split(","):
        bits = part.strip().split(":")
        if len(bits) < 2 or bits[1] not in intents:
            fail(f"bad leg '{part}' — format is "
                 "SYMBOL:position_intent[:ratio], intent one of "
                 f"{sorted(intents)}")
        legs.append({"symbol": bits[0],
                     "position_intent": bits[1],
                     "side": intents[bits[1]],
                     "ratio_qty": int(bits[2]) if len(bits) > 2 else 1})
    return legs


def cmd_spread(args, cfg, ledger, venue) -> None:
    if not args.thesis or len(args.thesis.strip()) < 20:
        fail("--thesis is required (>=20 chars)")
    legs = _parse_legs(args.legs)
    violations = check_bounds(cfg, ledger)
    if violations:
        log.warn("order_blocked", legs=args.legs, violations=violations)
        ledger.record_event("trade_tool", "order_blocked",
                            {"legs": args.legs, "violations": violations})
        fail("order blocked", violations=violations)
    session_id = os.environ.get("MIND_SESSION_ID")
    order_id = ledger.record_order(
        venue=cfg["venue"], venue_order_id=None,
        symbol=legs[0]["symbol"], side="mleg", order_type=args.type,
        qty=args.qty, limit_price=args.limit_price, status="pending",
        session_id=session_id, legs=legs, thesis=args.thesis)
    log.info("order_intent_recorded", order_id=order_id, side="mleg",
             legs=args.legs, leg_count=len(legs), qty=args.qty,
             order_type=args.type, limit_price=args.limit_price)
    try:
        result = venue.place_mleg_order(
            legs, qty=args.qty, order_type=args.type,
            limit_price=args.limit_price)
    except Exception as e:
        log.error("order_place_failed", exc=e, order_id=order_id,
                  side="mleg", legs=args.legs, qty=args.qty)
        ledger.update_order(order_id, status="error")
        fail(f"venue rejected the spread: {type(e).__name__}: {e}")

    structure_id = result["venue_order_id"]
    log.info("order_placed", order_id=order_id, venue_order_id=structure_id,
             structure_id=structure_id, side="mleg", legs=args.legs,
             leg_count=len(legs), qty=args.qty,
             limit_price=args.limit_price, status=result["status"])
    ledger.update_order(order_id, venue_order_id=structure_id,
                        status=result["status"],
                        structure_id=structure_id,
                        filled_qty=result["filled_qty"],
                        filled_avg_price=result["filled_avg_price"],
                        legs=result.get("legs") or legs)
    trade_ids = []
    filled_now = result["status"] == "filled"
    if filled_now:
        # One ledger trade per leg, grouped by structure_id, so partial
        # exits and per-leg settlement stay representable. Leg fill
        # prices come from the venue's per-leg records when present.
        leg_fills = {(l.get("symbol")): l for l in (result.get("legs") or [])}
        for leg in legs:
            lf = leg_fills.get(leg["symbol"]) or {}
            side = "long" if leg["side"] == "buy" else "short"
            trade_ids.append(ledger.open_trade(
                venue=cfg["venue"], symbol=leg["symbol"], side=side,
                qty=(args.qty * leg["ratio_qty"]),
                entry_price=float(lf.get("filled_avg_price") or 0) or None,
                thesis=args.thesis, structure_id=structure_id,
                session_id_open=session_id,
                meta={"multiplier": 100,
                      "position_intent": leg["position_intent"]}))
    out({"ok": result["status"] not in ("rejected",),
         "order": result | {"raw": "(stored in ledger)"},
         "structure_id": structure_id,
         "trade_ids": trade_ids,
         "resting": not filled_now,
         "note": None if filled_now else
         "spread is working at the venue; the sentinel adopts the fill "
         "into per-leg ledger trades and wakes you. Do not wait for it "
         "in this session."})


def cmd_close(args, cfg, ledger, venue) -> None:
    trades = ledger.open_trades()
    if args.trade_id:
        matches = [t for t in trades if t["id"] == args.trade_id]
    else:
        matches = [t for t in trades if t["symbol"] == args.symbol]
    if not matches:
        fail("no matching open trade in ledger",
             open_trades=[{k: t[k] for k in ("id", "symbol", "side", "qty")}
                          for t in trades],
             hint="if the venue holds this position, run `trade reconcile "
                  "--heal` first — the ledger may not have adopted a fill "
                  "yet")
    if len(matches) > 1:
        # --symbol resolving silently to one lot leaves the others
        # uncovered; multi-lot symbols demand an explicit --trade-id.
        fail(f"{args.symbol} has {len(matches)} open trades — --symbol is "
             "ambiguous",
             open_trades=[{k: t[k] for k in ("id", "symbol", "side", "qty")}
                          for t in matches],
             hint="close each lot explicitly with --trade-id")
    t = matches[0]
    session_id = os.environ.get("MIND_SESSION_ID")
    close_side = "sell" if t["side"] == "long" else "buy"

    # One exit at a time: an exit already resting at the venue reserves
    # that quantity; a second one fails less legibly at the venue.
    marks = ",".join("?" for _ in OPEN_ORDER_STATUSES)
    resting = ledger.query(
        "SELECT id, venue_order_id, order_type, stop_price, limit_price, "
        f"status FROM orders WHERE trade_id=? AND side=? AND status IN ({marks})",
        (t["id"], close_side, *OPEN_ORDER_STATUSES))
    if resting:
        fail("an exit order for this trade is already resting at the venue",
             resting=resting,
             hint="cancel it first (`trade cancel --order-id "
                  f"{resting[0]['venue_order_id']}`) or leave it armed — "
                  "the sentinel adopts its fill automatically")

    if args.type in ("stop", "stop_limit"):
        # Resting protective exit parked AT THE VENUE: it fires even
        # while the agent sleeps, with no wake latency. The sentinel
        # adopts the fill and closes the ledger trade when it executes.
        if not args.stop_price:
            fail("--stop-price is required for a resting stop/stop_limit "
                 "exit")
        if args.type == "stop_limit" and not args.limit_price:
            fail("--limit-price is required for stop_limit")
        order_id = ledger.record_order(
            venue=cfg["venue"], venue_order_id=None, symbol=t["symbol"],
            side=close_side, order_type=args.type, qty=t["qty"],
            limit_price=args.limit_price, stop_price=args.stop_price,
            status="pending", session_id=session_id, trade_id=t["id"],
            thesis=f"PROTECTIVE EXIT (resting {args.type}) for trade "
                   f"{t['id']}: {args.reason or 'protective exit'}")
        log.info("order_intent_recorded", order_id=order_id,
                 trade_id=t["id"], symbol=t["symbol"], side=close_side,
                 order_type=args.type, qty=t["qty"],
                 limit_price=args.limit_price, stop_price=args.stop_price)
        try:
            result = venue.place_order(
                t["symbol"], close_side, args.type, qty=t["qty"],
                limit_price=args.limit_price, stop_price=args.stop_price,
                time_in_force="gtc")
        except Exception as e:
            log.error("order_place_failed", exc=e, order_id=order_id,
                      trade_id=t["id"], symbol=t["symbol"], side=close_side,
                      order_type=args.type)
            ledger.update_order(order_id, status="error")
            fail(f"venue rejected the protective exit: "
                 f"{type(e).__name__}: {e}",
                 hint="some instruments only accept day-tif or market/"
                      "limit orders — a sentinel price trigger in "
                      "triggers.json is the venue-independent fallback")
        ledger.update_order(order_id,
                            venue_order_id=result["venue_order_id"],
                            status=result["status"])
        log.info("order_placed", order_id=order_id,
                 venue_order_id=result["venue_order_id"], trade_id=t["id"],
                 symbol=t["symbol"], side=close_side, order_type=args.type,
                 qty=t["qty"], limit_price=args.limit_price,
                 stop_price=args.stop_price, status=result["status"])
        out({"ok": result["status"] not in ("rejected",),
             "resting_exit": result | {"raw": "(stored in ledger)"},
             "trade_id": t["id"]})
        return

    if args.limit_price:
        fail("`close` has no plain-limit type — --limit-price is only "
             "valid with --type stop_limit. A bare close is a market "
             "order.",
             hint="for a limit exit, place it with `trade open` on the "
                  "opposite side, or arm a price trigger and close on the "
                  "wake")

    # Close THIS trade's qty — never the venue's whole symbol position
    # (two ledger lots on one symbol must survive each other's exits).
    result = venue.place_order(t["symbol"], close_side, "market",
                               qty=t["qty"])
    log.info("order_placed", venue_order_id=result["venue_order_id"],
             trade_id=t["id"], symbol=t["symbol"], side=close_side,
             order_type="market", qty=t["qty"], status=result["status"],
             filled_qty=result["filled_qty"])
    final = dict(result)
    if result["venue_order_id"] and not result.get("filled_avg_price"):
        for _ in range(3):
            time.sleep(1)
            try:
                o = venue.get_order(result["venue_order_id"])
            except Exception as e:
                log.warn("fill_poll_failed",
                         venue_order_id=result["venue_order_id"],
                         trade_id=t["id"], error=repr(e))
                break
            if o.get("filled_avg_price"):
                final.update({k: o.get(k) for k in
                              ("status", "filled_qty", "filled_avg_price",
                               "fees")})
                break
    # qty records the SUBMITTED quantity; filled_qty records the truth.
    # Recording a mid-fill partial as the order size makes the row lie
    # about intent forever.
    ledger.record_order(
        venue=cfg["venue"], venue_order_id=final["venue_order_id"],
        symbol=t["symbol"], side=close_side, order_type="market",
        qty=t["qty"], status=final["status"],
        filled_qty=final.get("filled_qty"),
        filled_avg_price=final.get("filled_avg_price"),
        fees=final.get("fees"), session_id=session_id, trade_id=t["id"],
        raw=result["raw"],
        thesis=f"CLOSE (market) for trade {t['id']}: "
               f"{args.reason or 'unspecified'}")

    if final.get("filled_avg_price"):
        exit_px = final["filled_avg_price"]
        fq = float(final.get("filled_qty") or 0)
        if 0 < fq < (t["qty"] or 0) - 1e-9:
            summary = ledger.split_close_trade(
                t["id"], filled_qty=fq, exit_price=exit_px,
                fees_add=final.get("fees") or 0,
                exit_reason=(args.reason or "unspecified")
                + f" [PARTIAL: {fq:g} of {t['qty']:g} filled; remainder "
                  "stays open]",
                session_id=session_id)
            log.info("split_close", trade_id=t["id"], symbol=t["symbol"],
                     filled_qty=fq, submitted_qty=t["qty"],
                     exit_price=exit_px)
        else:
            summary = ledger.close_trade(
                t["id"], exit_price=exit_px,
                fees_add=final.get("fees") or 0,
                exit_reason=args.reason or "unspecified",
                session_id=session_id)
            log.info("trade_closed", trade_id=t["id"], symbol=t["symbol"],
                     qty=t["qty"], exit_price=exit_px)
        out({"ok": True, "closed": summary,
             "order": final | {"raw": "(stored in ledger)"}})
    else:
        # The ledger closes trades on FILLS, not intents — a close
        # recorded at the quote price is wrong forever once the real
        # fill differs. The sentinel adopts the actual fill and closes
        # the trade at the real price, carrying this reason.
        log.info("close_submitted", trade_id=t["id"], symbol=t["symbol"],
                 venue_order_id=final["venue_order_id"],
                 status=final["status"])
        out({"ok": True, "trade_id": t["id"],
             "closing": final | {"raw": "(stored in ledger)"},
             "note": "close order submitted; fill not confirmed yet. The "
                     "trade stays OPEN in the ledger until the sentinel "
                     "adopts the actual fill (typically seconds). Do NOT "
                     "wait for it in this session."})


def cmd_reconcile(args, cfg, ledger, venue) -> None:
    """Diff live venue positions vs ledger open trades; --heal updates
    the ledger to match venue reality (the venue is always the source of
    truth). A WHOLE unit is never dust: one contract at a few cents is a
    real position, and filtering it away makes reconcile lie."""
    live = {p["symbol"]: p for p in venue.positions()
            if abs(p.get("market_value") or 0) >= 1.0
            or abs(p.get("qty") or 0) >= 1}
    open_trades = ledger.open_trades()
    by_symbol: dict[str, list] = {}
    for t in open_trades:
        by_symbol.setdefault(t["symbol"], []).append(t)

    report, healed = [], []
    for sym in sorted(set(live) | set(by_symbol)):
        venue_qty = abs(live.get(sym, {}).get("qty", 0.0) or 0.0)
        ledger_qty = sum(abs(t["qty"] or 0) for t in by_symbol.get(sym, []))
        diverged = abs(venue_qty - ledger_qty) > max(1e-9, venue_qty * 1e-4)
        row = {"symbol": sym, "venue_qty": venue_qty,
               "ledger_qty": ledger_qty, "diverged": diverged}
        if diverged and args.heal:
            ts = by_symbol.get(sym, [])
            if len(ts) == 1 and venue_qty > 0:
                ledger.update_trade(ts[0]["id"], qty=venue_qty)
                row["healed"] = f"trade {ts[0]['id']} qty -> {venue_qty}"
                healed.append(sym)
            elif not ts and venue_qty > 0:
                p = live[sym]
                tid = ledger.open_trade(
                    venue=cfg["venue"], symbol=sym,
                    side=p.get("side", "long"), qty=venue_qty,
                    entry_price=p.get("entry_price"),
                    thesis="RECONCILE: position found at venue with no "
                           "ledger trade — origin unknown, review required",
                    session_id_open=os.environ.get("MIND_SESSION_ID"),
                    meta={"multiplier": p.get("multiplier") or 1})
                row["healed"] = f"created trade {tid}"
                healed.append(sym)
            else:
                row["healed"] = ("SKIPPED: multiple ledger trades for one "
                                 "venue position — heal manually")
        report.append(row)
    pending = ledger.query(
        "SELECT id, symbol, side, status FROM orders "
        "WHERE status IN ('pending','error') ORDER BY ts DESC LIMIT 10")
    diverged_rows = [r for r in report if r["diverged"]]
    for r in diverged_rows:
        log.warn("reconcile_divergence", symbol=r["symbol"],
                 venue_qty=r["venue_qty"], ledger_qty=r["ledger_qty"],
                 healed=r.get("healed"))
    log.info("reconcile", heal=bool(args.heal),
             divergence_count=len(diverged_rows),
             clean_count=len(report) - len(diverged_rows),
             healed_count=len(healed), stuck_orders=len(pending))
    out({"ok": True, "divergence_count": len(diverged_rows),
         "diverged": diverged_rows,
         "clean": [r["symbol"] for r in report if not r["diverged"]],
         "stuck_orders": pending, "healed": healed,
         "hint": "run with --heal to adopt venue reality into the ledger"})


def cmd_status(cfg, ledger) -> None:
    halt = (Path(cfg["paths"]["state"]) / "HALT").exists()
    cap = int((cfg.get("bounds") or {}).get("max_orders_per_hour", 60))
    out({
        "halt": halt,
        "equity_latest_snapshot": ledger.latest_equity(),
        "realized_pnl_today": round(
            ledger.realized_pnl_since(day_start_ts()), 2),
        "open_trades": len(ledger.open_trades()),
        "orders_last_hour": ledger.orders_in_last(3600),
        "max_orders_per_hour": cap,
        "note": "the only bounds are HALT and orders/hour — risk doctrine "
                "is yours, not the engine's",
    })


def main() -> None:
    p = argparse.ArgumentParser(prog="trade")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("account", "positions", "orders", "movers", "status"):
        sub.add_parser(name)

    q = sub.add_parser("quote")
    q.add_argument("symbols", nargs="+")
    oq = sub.add_parser("oquote")
    oq.add_argument("symbols", nargs="+")

    ch = sub.add_parser("chain")
    ch.add_argument("--underlying", required=True)
    ch.add_argument("--type", choices=["call", "put"])
    ch.add_argument("--exp-gte")
    ch.add_argument("--exp-lte")
    ch.add_argument("--strike-gte", type=float)
    ch.add_argument("--strike-lte", type=float)

    co = sub.add_parser("contracts")
    co.add_argument("--underlying", required=True)
    co.add_argument("--type", choices=["call", "put"])
    co.add_argument("--exp-gte")
    co.add_argument("--exp-lte")
    co.add_argument("--strike-gte", type=float)
    co.add_argument("--strike-lte", type=float)

    o = sub.add_parser("open")
    o.add_argument("--symbol", required=True)
    o.add_argument("--side", required=True, choices=["long", "short"])
    o.add_argument("--qty", type=float)
    o.add_argument("--notional", type=float)
    o.add_argument("--type", default="market",
                   choices=["market", "limit", "stop", "stop_limit"])
    o.add_argument("--limit-price", type=float)
    o.add_argument("--stop-price", type=float)
    o.add_argument("--tif", default="day", choices=["day", "gtc"])
    o.add_argument("--thesis", required=True)

    sp = sub.add_parser("spread")
    sp.add_argument("--legs", required=True,
                    help='e.g. "OCC:sell_to_open:1,OCC:buy_to_open:1"')
    sp.add_argument("--qty", type=int, required=True)
    sp.add_argument("--type", default="limit", choices=["market", "limit"])
    sp.add_argument("--limit-price", type=float,
                    help="net price: positive = debit paid, negative = "
                         "credit received")
    sp.add_argument("--thesis", required=True)

    c = sub.add_parser("close")
    c.add_argument("--symbol")
    c.add_argument("--trade-id", type=int)
    c.add_argument("--reason")
    c.add_argument("--type", default="market",
                   choices=["market", "stop", "stop_limit"])
    c.add_argument("--stop-price", type=float)
    c.add_argument("--limit-price", type=float)

    x = sub.add_parser("cancel")
    x.add_argument("--order-id", required=True)

    rec = sub.add_parser("reconcile")
    rec.add_argument("--heal", action="store_true")

    rc = sub.add_parser("recent")
    rc.add_argument("--days", type=int, default=7)

    nw = sub.add_parser("news")
    nw.add_argument("--symbols")
    nw.add_argument("--hours", type=float, default=24)
    nw.add_argument("--limit", type=int, default=30)

    # `trade events` exists so self-verification never depends on
    # hand-written SQL against a schema recalled from memory — the right
    # thing is the easy thing.
    evp = sub.add_parser("events")
    evp.add_argument("--minutes", type=float, default=15)
    evp.add_argument("--kind")
    evp.add_argument("--limit", type=int, default=50)

    # `trade notify` is the agent's one-command bridge to the owner's
    # window: it records an event the interface manager wakes on. The
    # summarizing is the manager's job — the agent just rings.
    nf = sub.add_parser("notify")
    nf.add_argument("message", nargs="?", default=None)

    rv = sub.add_parser("reviewed")
    rv.add_argument("trade_id", type=int)

    args = p.parse_args()
    cfg = load_config()

    global log
    logs_dir = (cfg.get("paths") or {}).get("logs")
    if logs_dir:
        os.environ.setdefault("JSONLOG_DIR", str(logs_dir))
    log = get_logger("trade")
    if os.environ.get("MIND_SESSION_ID"):
        log = log.bind(session_id=os.environ["MIND_SESSION_ID"])

    ledger = Ledger(cfg["paths"]["ledger"])
    venue = Venue()

    legs_spec = getattr(args, "legs", None)
    log.info("command", cmd=args.cmd,
             symbol=getattr(args, "symbol", None),
             symbols=getattr(args, "symbols", None),
             underlying=getattr(args, "underlying", None),
             side=getattr(args, "side", None),
             qty=getattr(args, "qty", None),
             notional=getattr(args, "notional", None),
             trade_id=getattr(args, "trade_id", None),
             order_id=getattr(args, "order_id", None),
             leg_count=len(legs_spec.split(",")) if legs_spec else None)

    try:
        if args.cmd == "account":
            a = venue.account()
            out({k: a[k] for k in ("equity", "cash", "positions_value",
                                   "buying_power", "options_approved_level",
                                   "options_buying_power")})
        elif args.cmd == "positions":
            out(venue.positions())
        elif args.cmd == "orders":
            out(venue.open_orders())
        elif args.cmd == "quote":
            out(venue.quotes(args.symbols))
        elif args.cmd == "oquote":
            out(venue.option_quotes(args.symbols))
        elif args.cmd == "chain":
            out(venue.option_chain(
                args.underlying, contract_type=args.type,
                expiration_gte=args.exp_gte, expiration_lte=args.exp_lte,
                strike_gte=args.strike_gte, strike_lte=args.strike_lte))
        elif args.cmd == "contracts":
            out(venue.option_contracts(
                args.underlying, contract_type=args.type,
                expiration_gte=args.exp_gte, expiration_lte=args.exp_lte,
                strike_gte=args.strike_gte, strike_lte=args.strike_lte))
        elif args.cmd == "movers":
            out(venue.movers())
        elif args.cmd == "status":
            cmd_status(cfg, ledger)
        elif args.cmd == "open":
            if args.qty is None and args.notional is None:
                fail("provide --qty or --notional")
            cmd_open(args, cfg, ledger, venue)
        elif args.cmd == "spread":
            cmd_spread(args, cfg, ledger, venue)
        elif args.cmd == "close":
            if not args.symbol and not args.trade_id:
                fail("provide --symbol or --trade-id")
            cmd_close(args, cfg, ledger, venue)
        elif args.cmd == "cancel":
            res = venue.cancel_order(args.order_id)
            rows = ledger.query(
                "SELECT id FROM orders WHERE venue_order_id=?",
                (args.order_id,))
            if rows:
                ledger.update_order(rows[0]["id"], status="canceled")
            log.info("cancel_requested", venue_order_id=args.order_id,
                     ledger_order_id=rows[0]["id"] if rows else None)
            out(res)
        elif args.cmd == "reconcile":
            cmd_reconcile(args, cfg, ledger, venue)
        elif args.cmd == "news":
            syms = args.symbols.split(",") if args.symbols else None
            out(venue.news(symbols=syms, since_hours=args.hours,
                           limit=args.limit))
        elif args.cmd == "events":
            since = time.time() - args.minutes * 60
            sql = ("SELECT rowid, datetime(ts,'unixepoch') AS t, source, "
                   "kind, detail FROM events WHERE ts >= ? ")
            params: list = [since]
            if args.kind:
                kinds = [k.strip() for k in args.kind.split(",") if k.strip()]
                sql += f"AND kind IN ({','.join('?' * len(kinds))}) "
                params += kinds
            sql += "ORDER BY ts DESC LIMIT ?"
            params.append(args.limit)
            rows = ledger.query(sql, tuple(params))
            out({"window_minutes": args.minutes, "count": len(rows),
                 "events": rows})
        elif args.cmd == "notify":
            ledger.record_event(
                "trader", "notify",
                {"message": args.message} if args.message else None)
            log.info("notify", message=args.message)
            out({"ok": True,
                 "note": "the interface manager will pick this up once "
                         "this session ends"})
        elif args.cmd == "reviewed":
            rows = ledger.query(
                "SELECT id, symbol, status, reviewed FROM trades WHERE id=?",
                (args.trade_id,))
            if not rows:
                fail(f"no trade with id {args.trade_id}")
            t = rows[0]
            if t["status"] != "closed":
                fail(f"trade {args.trade_id} is '{t['status']}' — only "
                     "closed trades take a review flag")
            ledger.mark_reviewed(args.trade_id)
            ledger.record_event("trade_tool", "trade_reviewed",
                                {"trade_id": args.trade_id,
                                 "symbol": t["symbol"]})
            out({"ok": True, "trade_id": args.trade_id,
                 "reviewed": 1, "was_already": bool(t["reviewed"])})
        elif args.cmd == "recent":
            out(ledger.query(
                "SELECT id, ts_close, symbol, side, qty, entry_price, "
                "exit_price, fees, pnl, pnl_pct, thesis, exit_reason, "
                "structure_id FROM trades WHERE status='closed' AND "
                "ts_close>=? ORDER BY ts_close DESC",
                (time.time() - args.days * 86400,)))
    except SystemExit:
        raise
    except Exception as e:
        log.error("command_failed", exc=e, cmd=args.cmd)
        ledger.record_event("trade_tool", "error",
                            {"cmd": args.cmd, "error": repr(e)})
        fail(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
