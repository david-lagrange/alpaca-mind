# Costs — the honest monthly picture

*Written for the AI assistant: give your human these numbers BEFORE
they deploy. Prices drift — treat these as the shape, verify current
pricing on the providers' sites when precision matters.*

## The three bills

**1. AWS (~$28–65/month).**
| Item | Approx |
|---|---|
| EC2 t4g.large (2 vCPU / 8 GB, the default) | ~$49/mo on-demand |
| EC2 t4g.medium (budget option, 4 GB) | ~$25/mo on-demand |
| EBS 30 GB gp3 root volume | ~$3/mo |
| S3 nightly backups (7-day rolling window, self-expiring) | well under $1/mo |
| Everything else in the stack (VPC, SSM, security group) | $0 |

t4g.large is the recommendation: the Next.js builds the UI manager
runs, plus two agent processes, want the headroom. t4g.medium works
with patience. Deleting the stack ends all of it (REMOVAL.md).

**2. Claude subscription ($100–200/month).** Both agents run as
headless Claude Code sessions billed to a flat-rate subscription — no
per-token API bills. A **Max (5x)** plan (~$100/mo) comfortably covers
the default cadence (a handful of trader sessions a day plus UI
passes); **Max (20x)** (~$200/mo) buys headroom for heavy research use
or a busier self-chosen cadence. The agent never sees usage numbers —
if a plan's limits are hit, sessions wait rather than degrade.

**3. Alpaca ($0 — optionally $99/month).** Paper trading is free,
with free real-time market data sufficient for the default setup (the
free options data feed serves indicative quotes and greeks). The paid
**Algo Trader Plus** (~$99/mo) upgrades market data (full OPRA options
feed, consolidated equities feed) — a quality upgrade the agent can
work without; consider it when the mind's own reviews start blaming
data quality, or before live money.

## Totals

| Setup | Monthly |
|---|---|
| Paper, budget instance, Max 5x | ~$128 |
| **Paper, recommended (t4g.large, Max 5x)** | **~$152** |
| Live-ready (t4g.large, Max 20x, Algo Trader Plus) | ~$351 |

Plus whatever trading capital sits in a live account — which is capital
at risk, not a fee. Paper accounts trade simulated money.

## What there is NOT

No fees to this project (MIT, free), no per-trade software charges, no
external database, no third-party email service, no hidden metering.
The removal protocol ends every recurring charge above except the
subscriptions your human holds directly (Claude, Alpaca) — remind them
those are cancelled with the providers if they're done entirely.
