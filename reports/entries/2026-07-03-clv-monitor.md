# 2026-07-03 · WS-1 — the forward CLV/λ accrual monitor (the self-running truth loop)

**One line:** the apparatus that makes "measure λ for real" run itself once dense capture is on —
each reading logs trajectory coverage, the λ̂+CI (proxy until coverage≥50%, REAL after), and the
**floor verdict** (does λ̂'s CI lower bound clear the pilot's 0.25 edge floor?). Today it reads
**EMPTY** (coverage 0%, deploy pending); it will climb through ACCRUING→MEASURED as data flows.

## What was built
`scripts/clv_monitor.py` — wraps `clv_lambda.measure` (which already auto-switches proxy→trajectory),
adds the temporal/state dimension, appends each reading to `reports/clv_accrual_log.jsonl` (append-only
trend), and emits an honest state machine: **EMPTY → ACCRUING → MEASURED**, with a **CLEARS/BELOW**
floor verdict only once coverage is trustworthy. `--selftest` PASS incl. the anti-laundering guard (a
high *proxy* λ̂ at 0% coverage must NOT read as CLEARS). `--history` prints the trend.

## Today's reading
`state EMPTY · coverage 0.0% · λ̂ 0.167 (proxy, NOT trustworthy) · CLV null p=0.0000 · explained 16.7%`
→ **VERDICT: EMPTY** — deploy Option B (`DENSE_CAPTURE=true`) to start accruing; λ stays a proxy until
then. This is the meter that turns the 2–4 week accrual into a tracked, honest λ̂ — the edge-reality
gate, one input to the full go/no-go (WS-2). Persistence (D7) still governs real money.

## How to run it forward
Once dense capture is deployed, run `clv_monitor.py` weekly (or wire it to the honest digest). When it
prints **MEASURED / CLEARS**, the edge-reality gate is met; **MEASURED / BELOW** means the edge is
bias, not information — the signal to pivot (WS-4 softness / WS-3 copyability point the way).
