#!/usr/bin/env python3
"""Print the Content-Length of one R2 object, or 0 if absent/unreachable.

Hand-rolled SigV4 HEAD so this works under the bare system python3 that launchd runs
the nightly with — no boto3, no venv. Used by prune-dumps.sh to prove a full dump is
really offsite before any local copy is deleted.

  python3 scripts/r2_head.py dumps/consensus-20260713-0400.sql.gz
"""
import datetime
import hashlib
import hmac
import os
import sys
import urllib.request

key = os.environ["R2_ACCESS_KEY_ID"]
secret = os.environ["R2_SECRET_ACCESS_KEY"]
host = f"{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
bucket = os.environ["R2_BUCKET"]
obj = sys.argv[1]

t = datetime.datetime.now(datetime.timezone.utc)
amz = t.strftime("%Y%m%dT%H%M%SZ")
ds = t.strftime("%Y%m%d")
payload = hashlib.sha256(b"").hexdigest()

canon = (
    "HEAD\n"
    f"/{bucket}/{obj}\n"
    "\n"
    f"host:{host}\nx-amz-content-sha256:{payload}\nx-amz-date:{amz}\n"
    "\n"
    "host;x-amz-content-sha256;x-amz-date\n"
    f"{payload}"
)
scope = f"{ds}/auto/s3/aws4_request"
sts = f"AWS4-HMAC-SHA256\n{amz}\n{scope}\n{hashlib.sha256(canon.encode()).hexdigest()}"

k = f"AWS4{secret}".encode()
for msg in (ds, "auto", "s3", "aws4_request"):
    k = hmac.new(k, msg.encode(), hashlib.sha256).digest()
sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()

req = urllib.request.Request(
    f"https://{host}/{bucket}/{obj}",
    method="HEAD",
    headers={
        "Host": host,
        "x-amz-date": amz,
        "x-amz-content-sha256": payload,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={key}/{scope}, "
            "SignedHeaders=host;x-amz-content-sha256;x-amz-date, "
            f"Signature={sig}"
        ),
    },
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print(r.headers.get("Content-Length", "0"))
except Exception:
    # Absent, unauthorized, or unreachable all mean the same thing to the caller: we
    # cannot prove the dump is offsite, so the caller must refuse to delete.
    print("0")
