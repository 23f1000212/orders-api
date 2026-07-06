import base64
import time
from collections import defaultdict
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ----------------------------
# CORS
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Constants
# ----------------------------
TOTAL_ORDERS = 59
RATE_LIMIT = 17
WINDOW = 10

# ----------------------------
# In-memory data
# ----------------------------
orders = [
    {"id": i, "description": f"Order {i}"}
    for i in range(1, TOTAL_ORDERS + 1)
]

idempotency = {}

client_hits = defaultdict(list)


# ----------------------------
# Rate limiter
# ----------------------------
def enforce_rate_limit(client_id: str):
    now = time.time()

    hits = [t for t in client_hits[client_id] if now - t < WINDOW]
    client_hits[client_id] = hits

    if len(hits) >= RATE_LIMIT:
        retry_after = max(1, int(WINDOW - (now - hits[0])) + 1)

        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(retry_after)
            },
        )

    hits.append(now)
    client_hits[client_id] = hits


# ----------------------------
# Home
# ----------------------------
@app.get("/")
def root():
    return {"message": "Orders API Running"}


# ----------------------------
# POST /orders
# ----------------------------
@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_client_id: str = Header("default", alias="X-Client-Id"),
):

    enforce_rate_limit(x_client_id)

    if not idempotency_key:
        idempotency_key = f"auto-{time.time_ns()}"

    if idempotency_key in idempotency:
        return idempotency[idempotency_key]

    order = {
        "id": f"ord_{len(idempotency)+1}"
    }

    idempotency[idempotency_key] = order

    return order


# ----------------------------
# GET /orders
# ----------------------------
@app.get("/orders")
def get_orders(
    limit: int = 10,
    cursor: Optional[str] = None,
    x_client_id: str = Header("default", alias="X-Client-Id"),
):

    enforce_rate_limit(x_client_id)

    if limit < 1:
        limit = 1

    start = 0

    if cursor:
        try:
            start = int(base64.b64decode(cursor).decode())
        except Exception:
            start = 0

    end = min(start + limit, TOTAL_ORDERS)

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end).encode()).decode()

    return {
        "items": orders[start:end],
        "next_cursor": next_cursor,
    }
