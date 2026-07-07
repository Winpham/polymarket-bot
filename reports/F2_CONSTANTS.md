# F2 on-chain constants — P0-B verified (2026-07-06)

Empirically decoded from real tracked-wallet OrderFilled receipts (40-fill probe).

## GATE 2 verdict: PASS
- `address_match_pct` = **100%** (proxy wallet is the OrderFilled `maker`/`taker` directly — no EOA map).
- `price_size_roundtrip`: 34/40 exact; **only 34/40 even at round-10dp** → 15% are multi-level
  VWAP fills the data-api aggregated. **Dedup layer = `source_scoped+collapse`** (three-layer),
  NOT tx-index rounding. Confirms the plan's rejection of the 2dp shortcut AND rules out round-10dp.
- No rate-limiting over 40 sequential receipts on the free RPC.

## Constants (store in config, not hard-coded — addresses vary)
- **RPC (free, working)**: `https://polygon-bor-rpc.publicnode.com` (requires a browser `User-Agent`;
  default python-urllib UA → 403). Fallbacks: `polygon.drpc.org`, `1rpc.io/matic`.
  DEAD: `polygon-rpc.com` (tenant disabled), `rpc.ankr.com/polygon` (auth required), `polygon.llamarpc.com` (empty).
- **OrderFilled topic0**: `0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee`
- **Observed exchange addresses** (NOT the "known" CTF constants): `0xe111180000d2663c0091e4f400237545b87b996b`,
  `0xe2222d279d744050d28e00520010520000310f59`. Addresses VARY across trades → F2 filters by
  `topic0 == OrderFilled` AND `maker|taker ∈ tracked wallets`, watches the observed address set,
  and LOGS any new address (no silent restriction).

## OrderFilled ABI (verified)
- 4 topics: `[topic0, orderHash, maker(indexed), taker(indexed)]`
- data (5×uint256): `[makerAssetId, takerAssetId, makerAmountFilled, takerAmountFilled, fee]`
- USDC = 6dp, shares = 6dp, assetId 0 = collateral (USDC).
- `makerAssetId==0` → maker paid USDC (BUY): price = makerAmt/takerAmt, size_usd = makerAmt/1e6, asset = takerAssetId.
- else → maker sold shares (SELL): price = takerAmt/makerAmt, size_usd = takerAmt/1e6, asset = makerAssetId.
- The ERC1155 CTF token contract (`0x4d97dcd97ec945f40cf65f87097ace5ea0476045`) also emits
  TransferSingle/Batch (topic0 `0x4a39dc06…`, `0x2e6bb91f…`) — NOT OrderFilled; ignore.
