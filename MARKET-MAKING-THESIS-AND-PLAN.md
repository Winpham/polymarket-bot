# Market-Making: thesis, evidence, and a staged plan to tap in (and maybe beat them)

**Status:** research + plan, 2026-07-03. Paper/sim only. No infra built. No real money.
Evidence in §2 is freshly computed and reproducible (`scripts/mm_premise_probe.sql`) — it
replaces the earlier *unpersisted* ad-hoc console numbers.

---

## 0. The question

The top leaderboard "sharps" we've spent months trying to *tail* aren't predicting and aren't
(mostly) arbitraging — they're **market-making**: resting quotes on both sides, earning the
spread + liquidity rewards thousands of times on huge volume, while staying ~directionally flat.
The user's instinct — *"they make money from market structure, not from being right"* — is
correct. This doc asks: **can we tap into that, and can we do it better than them?**

Short answer: **The premise is real and now quantified. But "become a market-maker and beat them"
is the wrong frame — it's a from-scratch infra business, pro-dominated, reward-compressed, and
legally barred for a US person. The ONE defensible, differentiated angle is narrow and testable:
use our weak-but-real directional signal to *skew* an MM's quotes so our inventory leans the right
way — turning the money-losing resolution-hold leg (which they run flat) into a smaller loss or a
gain. That is the only place we could plausibly do it "better." Everything below stages a
cheap, paper-only path to kill or prove exactly that, before a dollar or a line of trading code.**

---

## 1. Three lanes — and why the label matters (confirmed)

| Lane | How you profit | Risk | Copyable by us? |
|---|---|---|---|
| **Prediction** | forecast outcome better than price | full directional | Yes if we have the info — **but we don't** (λ≈0.15, mostly favorite-longshot bias; nothing certified) |
| **Arbitrage** | buy YES+NO for sum < $1 → locked | none | Yes if fast — **gone in ms; unreachable at our 2-min poll** |
| **Market-making** | rest both sides, earn spread + rewards | inventory + adverse selection | **Only by becoming a maker** — no "tail them faster" version exists |

The label matters because it dictates the *only* way in. If it were arb, the play would be a
latency race. Because it's **market-making, the spread they earn is exactly the spread a follower
pays** — there is no tailing version at all. You have to *become the maker*.

## 2. What they actually do — evidence from our own 1.33M fills

`trader_fills`: 1,329,882 fills · 420 wallets · 15,873 markets · 2022→2026. Two archetypes,
both confirmed with fresh numbers (`scripts/mm_premise_probe.sql`):

**Archetype A — buy-both-sides, hold to resolution (the flagship whale).**
`0x204f72…` — **$38.3M volume, 78k fills, ~19,600 fills/day, sell_frac = 0.000, twosided 0.59.**
It *never sells*; it rests bids on both outcomes and holds to resolution.
- True two-leg price sum: **avg 1.0246, median 0.9974, 53.3% of markets locked (sum < $1)** over
  576 resolved paired markets. → **Not arbitrage** (avg > 1, only half locked) and **not
  prediction** (holds both sides).
- Realized **resolution-hold ROI = −4.53%** (−$1.6M) over 898 paired markets; profitable on only
  51.9% (coin-flip). Peers vary (−9.5% to +6%), but the biggest, highest-churn bot **loses on the
  hold.** A rational bot churning $38M that loses on inventory is only explicable if the
  **invisible leg — Polymarket's liquidity-rewards program — is the actual profit engine.** We
  cannot see reward income in our data; we infer it from the negative hold + the rational churn.

**Archetype B — classic round-trip spread capture.**
`0xe9076a…` — 177k fills, 44k/day, sell_frac 0.154, across 6,280 markets. On the same token it
**buys low and sells high: avg (sell − buy) price = +7.05¢** over **4,438 round-tripped tokens.**
Textbook bid-ask capture.

**Bottom line of the evidence:** the market-making thesis is *directionally confirmed and
quantified* — but note the honesty limits (§6): no maker/taker flag, 10k-offset backfill
truncation on exactly these whales, poll-gap incompleteness, and **reward income is off-book so
we can never compute their true total P&L from our data.** This is a strong hypothesis, not a
certification.

## 3. Can we tap in? The hard gates (all external, all real)

From primary-source research on Polymarket's 2026 mechanics:

1. **We have zero trading infra.** The whole system is read-only: no wallet, no EIP-712 signing,
   no CLOB auth, no order lifecycle, and we don't even store the *bid* side of the book (only
   best-ask + mid). To rest one quote we build the entire trading half from scratch (signing,
   order place/cancel/replace, L2 book pipeline, inventory tracking, an MM risk engine, a
   low-latency loop replacing the 2-min REST poll).
2. **The 0-fee, reward-farming golden era is OVER (2026).** Taker fees rolled out; **Jump and
   Wintermute entered** early/mid 2026; the canonical open-source MM bot (`warproxxx/poly-maker`)
   now carries its author's warning: *"in today's market, this bot is not profitable and will
   lose money."* Multiple first-person operators report net-zero-to-negative. Pure symmetric MM /
   reward-farming is **not reliably +EV for a small operator anymore.**
3. **Latency wall on the good markets.** Pros colocate at ~0.36ms; retail is 10–100ms. Fast/
   event-driven markets (crypto up-down, live sports) are unwinnable for us. Only slow, long-dated,
   low-vol markets are latency-tolerant — and their reward pools are small.
4. **Resolution tail risk = the dominant blow-up**, via UMA oracle disputes (Venezuela, Ukraine
   mineral deal ~$7M, Zelenskyy-suit). One bad resolution zeroes a held position. This is the
   *same directional risk we've proven we cannot forecast.*
5. **US-person ToS prohibition.** Polymarket.com bars US persons from trading. Tue is US-located.
   **This is a hard legal gate on live deployment** — not a technical one we can engineer around.
   (Polymarket US is a separate regulated venue with different economics; a separate question.)
6. **Capital floor.** Practitioner consensus: **$5k is too small** (monitoring overhead > profit);
   **~$50k is the plausible floor**, and only paired with a genuine edge. Honest expectation for a
   good small operator: **~10% annualized down to net-zero, with a fat left tail.**

Any ONE of {infra-from-zero, US-ToS, latency, reward-compression} is close to disqualifying for
"out-compete the pros at their own game." Together they close that door. **We will not win a
symmetric market-making race.**

## 4. Can we do it BETTER? The one differentiated axis: signal-skewed quoting

The only lane where we have something they structurally *don't*:

- **They run their directional leg ~flat** — that's why the flagship loses −4.5% on resolution
  holds (it leans inventory ~randomly). Their profit is spread + rewards, *despite* the hold.
- **We have a weak-but-real directional signal** — the favorite-longshot / "fade overhyped
  favorites" edge (WS-4: soccer/directional/band5 net +8.2%, z −4.57; consensus-favorite lean).
  It is **too weak to bet directionally** (must overcome the full spread + fee) — which is why our
  prediction track is dead. **But an MM doesn't need to beat the spread; it already earns it.** It
  only needs the signal to bias *which side fills* and *which way inventory leans* — a **far lower
  bar.** This is exactly the case where a dead directional signal gets a second life.

This is established theory, not our invention:
- **Avellaneda-Stoikov (2008):** MM quotes around a *reservation price* that leans against
  inventory — the exact hook where a signal is injected.
- **Cartea & Wang, "Market Making with Alpha Signals" (2020):** an MM with a noisy short-horizon
  drift signal shifts its reservation price and quotes asymmetric offsets — improves P&L (higher
  mean, lower variance) **across signal qualities, including weak/noisy signals.**
- **Polymarket structurally permits it:** fully independent one-sided/arbitrary quotes, batch
  cancel/replace, post-only. Counter-force: observable skew leaks your signal to "skew sniffers,"
  so optimal skew is *bounded* — realize most of it via **size asymmetry inside the reward band**
  rather than obvious one-sided offsets (keeps near-full reward credit *and* a directional lean).

**The crisp, falsifiable thesis:** the flagship loses −4.5% on holds because it leans inventory
randomly. If our signal can turn a two-sided quoter's resolution-hold ROI from −4.5% toward −2% /
0% / positive, then **at the same reward income we out-earn them.** The entire "do it better"
claim reduces to one measurable question: *does our signal improve the resolution-hold ROI of a
two-sided quoter, out-of-sample, belief-blind, net of fees and adverse selection?* Nothing else
about market-making is differentiated for us — this is.

## 5. The plan — staged, cheap-first, kill-gated (nothing irreversible until proven)

Aligned with our standing posture: confidence-gated, reversible probes first, no real money and
no trading-code build until the edge is certified in sim.

### Stage 0 — Certify the premise *(DONE, this run)*
Persisted `scripts/mm_premise_probe.sql`; confirmed both archetypes and the negative resolution
hold on the flagship. **Gate: do top wallets actually run a two-sided, reward-dependent, hold-
losing structure? → YES (directionally). PASSED.** Remaining Stage-0 hardening (optional, cheap):
re-run the paired-sum / hold-ROI across *all* two-sided wallets with a proper null (shuffle
outcome labels), and quantify the 10k-truncation bias on the top whales.

### Stage 1 — The decisive experiment: does signal-skew beat naive MM in sim? *(free, ~1–3 wks, read-only)*
Build a **paper MM backtest sandbox — no wallet, no orders, nothing on-chain.**
1. **Capture the real order book, read-only.** Subscribe to the CLOB market websocket
   (`wss://ws-subscriptions-clob.polymarket.com/ws/market`) for a chosen set of slow/long-dated
   sports & props markets; store **L2 snapshots (both sides + sizes)** and the reward-band params
   (`RewardsMaxSpread`, `RewardsMinSize`, tick size) per market. This is the missing data pipeline
   — but it costs nothing, needs no wallet, and is fully reversible.
2. **Simulate three quoters** over the captured book + resolutions: (a) **naive symmetric MM**
   (Avellaneda-Stoikov baseline), (b) **signal-skewed MM** (inject the fade-favorite / consensus
   signal into the reservation price, realize skew as size-asymmetry inside the reward band),
   (c) **do-nothing**. Score each with a realistic fill model (informed flow picks off stale
   quotes), the **actual reward formula** `S=((v−s)/v)²·b` with the single-sided penalty c=3.0,
   the **current taker/maker fee schedule**, and true resolution outcomes.
3. **Gate (the whole decision):** does signal-skew beat naive MM **and** clear zero after fees +
   adverse selection + resolution holds, **out-of-sample and belief-blind** (shuffle the signal →
   edge must vanish)? Sizing/persistence held to the same bar as everything else in this repo.
   - **RED** → stop. We've learned the ceiling for ~$0 and no irreversible build. Log it and move on.
   - **GREEN** → the edge is real in sim; proceed to a Tue decision — *not* to auto-deployment.

### Stage 2 — Tue's decision only (do NOT pre-build)
If Stage 1 is green, the remaining gates are **legal, capital, and infra**, and they are genuinely
Tue's call, not the model's:
- **Legal:** US-person ToS on Polymarket.com is a hard barrier. Options are Tue's to weigh
  (jurisdiction, the separate regulated Polymarket US venue, or shelving live deployment and
  keeping this as a validated-but-unfielded result). **The model builds no signing/order code
  until Tue clears this.**
- **Capital:** ~$50k floor for the economics to matter; fat left tail (one bad UMA resolution).
- **Infra:** only then build the trading half (signing, order lifecycle, inventory, low-latency
  loop) — behind the existing `pilot.rs` OrderGate stub, default-off, one-approval-away, paper-
  shadow before live.

## 6. Honest risk register — what kills this

- **Reward income is off-book.** We infer the profit engine from a negative hold + rational churn;
  we cannot measure their true P&L. If their real edge is *inside-the-band size games we can't
  see*, our sim will misprice it. → Stage 1 must model rewards from the *published formula*, not
  from their P&L.
- **Our signal may not survive as an MM input.** It's weak (λ≈0.15) and WC-concentrated; the
  fade-favorite cell is one FDR survivor. The lower MM bar helps, but "helps a weak signal" ≠
  "clears zero after adverse selection." Stage 1 is designed to catch a NULL here cheaply.
- **Adverse selection + resolution tail** are the real killers and are *harder* for us than for
  colocated pros. Our only mitigation is trading slow markets and quoting conservatively — which
  caps the reward pool we can reach.
- **Reward compression continues.** Jump/Wintermute are already in; pools shrink. A green Stage 1
  today may be red in six months. Treat any go as time-boxed and re-validated.
- **Data limits on the premise itself** (no maker/taker flag, 10k truncation, poll gaps) — Stage 0
  hardening should quantify these before over-trusting the −4.5% number.

## 7. Recommendation

**Do not pivot to becoming a market-maker.** Do run **Stage 1** — the paper-only book-capture +
signal-skew sim — because it is cheap, reversible, and answers the single load-bearing question
(*can our otherwise-dead directional edge make a two-sided quoter's inventory lean profitably?*).
If it's red, we've bought a definitive answer for ~$0. If it's green, we hand Tue a validated
result and a clean legal/capital decision — having built nothing we'd regret.

The honest one-liner: **we can't out-race them at market-making, but the one thing they leave on
the table is directional skew — and testing whether our weak signal can pick it up costs nothing
but a read-only websocket and a backtest.** That is the whole opportunity, and the whole plan.
