#!/usr/bin/env python3
"""
US ORDER CLIENT — interface + DISABLED stub. NO LIVE ORDER IS EVER SENT FROM THIS FILE.

Polymarket US auth is HMAC (keyId + secretKey, issued after KYC). A live order path is exactly the
thing that must NOT exist until (a) the pre-registered forward gate passes and (b) Tue explicitly
authorises it with his own credentials. So this file defines the INTERFACE the rest of the system
codes against, and a stub that HARD-REFUSES to transmit. Wiring a real transport is a deliberate,
authorised, reviewed change — never an accident.

Design guarantees encoded here:
  * `LiveUSOrderClient.submit()` raises unless `armed=True` AND real credentials are present AND an
    explicit `i_understand_this_spends_real_money=True` is passed. Default construction cannot trade.
  * Idempotency: every order carries a client-generated `idempotency_key`; a resubmit with the same
    key must be a no-op at the venue (prevents double-fills on retry).
  * The PAPER client implements the same interface and only records — that is what runs today.

  ./us_order_client.py --self-test
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Order:
    us_slug: str
    side: str                 # 'BUY'
    size_usd: float
    limit_price: float        # never a market order — always a limit at/through the ask
    idempotency_key: str      # dedupe at the venue


@dataclass(frozen=True)
class OrderResult:
    accepted: bool
    venue_order_id: str
    detail: str


class OrderClient:
    """Interface. Both paper and live implement submit()."""
    def submit(self, order: Order, **kw) -> OrderResult:      # pragma: no cover
        raise NotImplementedError


class PaperOrderClient(OrderClient):
    """Records intended orders. This is what runs today — no venue, no money."""
    def __init__(self):
        self._seen = {}      # idempotency_key -> OrderResult

    def submit(self, order: Order, **kw) -> OrderResult:
        if order.idempotency_key in self._seen:
            return self._seen[order.idempotency_key]          # idempotent
        res = OrderResult(True, f"paper-{len(self._seen)+1}", "recorded_paper_only")
        self._seen[order.idempotency_key] = res
        return res


class LiveUSOrderClient(OrderClient):
    """DISABLED by construction. Refuses to transmit unless every safety latch is set."""
    def __init__(self, key_id: str | None = None, secret_key: str | None = None,
                 armed: bool = False):
        self.key_id = key_id
        self.secret_key = secret_key
        self.armed = armed

    def submit(self, order: Order, i_understand_this_spends_real_money: bool = False,
               **kw) -> OrderResult:
        # Three independent latches, all required. Any one missing => refuse.
        if not self.armed:
            raise RuntimeError("LiveUSOrderClient is not armed — refusing to send a real order")
        if not (self.key_id and self.secret_key):
            raise RuntimeError("no US credentials present — refusing to send a real order")
        if not i_understand_this_spends_real_money:
            raise RuntimeError("explicit real-money acknowledgement required — refusing")
        # Even with all latches, transport is intentionally NOT implemented here. Wiring it is a
        # separate, authorised, reviewed change after the forward gate passes.
        raise NotImplementedError(
            "live transport intentionally unimplemented — gate must pass + Tue must wire it")


def self_test():
    o = Order("atp-a-b-2026-07-15", "BUY", 50.0, 0.88, "idem-1")

    # paper client records + is idempotent
    pc = PaperOrderClient()
    r1 = pc.submit(o)
    r2 = pc.submit(o)                       # same key
    assert r1.accepted and r1.venue_order_id == r2.venue_order_id, "paper must be idempotent"

    # live client refuses at every latch
    lc = LiveUSOrderClient()               # default: disarmed, no creds
    for kwargs in ({}, {"i_understand_this_spends_real_money": True}):
        try:
            lc.submit(o, **kwargs)
            raise AssertionError("disarmed live client must REFUSE")
        except RuntimeError:
            pass

    armed_nocreds = LiveUSOrderClient(armed=True)
    try:
        armed_nocreds.submit(o, i_understand_this_spends_real_money=True)
        raise AssertionError("armed but no creds must REFUSE")
    except RuntimeError:
        pass

    # fully-latched still refuses (transport unimplemented on purpose)
    full = LiveUSOrderClient(key_id="k", secret_key="s", armed=True)
    try:
        full.submit(o, i_understand_this_spends_real_money=True)
        raise AssertionError("transport must be unimplemented")
    except NotImplementedError:
        pass

    print("self-test OK  (paper idempotent; live client refuses at every latch — no money path)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    ap.print_help()
