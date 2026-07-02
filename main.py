import time
import uuid
from collections import defaultdict, deque
from typing import Optional

from fastapi import FastAPI, Header, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

TOTAL_ORDERS = 59
RATE_LIMIT = 17
WINDOW = 10  # seconds

app = FastAPI(title="Orders API")

# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Storage
# -----------------------------
idempotency_store = {}

client_requests = defaultdict(deque)

catalog = [
    {
        "id": i,
        "item": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]


# -----------------------------
# Models
# -----------------------------
class OrderRequest(BaseModel):
    item: str


# -----------------------------
# Rate Limiter
# -----------------------------
def rate_limit(client_id: str):

    now = time.time()

    bucket = client_requests[client_id]

    while bucket and now - bucket[0] >= WINDOW:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT:

        retry_after = max(
            1,
            int(WINDOW - (now - bucket
