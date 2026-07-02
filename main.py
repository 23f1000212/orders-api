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
# In-memory storage
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
def check_rate_limit(client_id: str):
    now = time.time()

    bucket = client_requests[client_id]

    # Remove expired timestamps
    while bucket and now - bucket[0] >= WINDOW:
        bucket.popleft()

    # Limit exceeded
    if len(bucket) >= RATE_LIMIT:
        retry_after = max(
            1,
            int(WINDOW - (now - bucket[0])) + 1
        )

        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded"
            },
            headers={
                "Retry-After": str(retry_after)
            }
        )

    bucket.append(now)

    return None


# -----------------------------
# Home
# -----------------------------
@app.get("/")
def home():
    return {
        "message": "Orders API Running"
    }


# -----------------------------
# Create Order
# -----------------------------
@app.post("/orders", status_code=201)
def create_order(
    order: OrderRequest,
    response: Response,
    idempotency_key: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key"
    ),
    x_client_id: str = Header(
        ...,
        alias="X-Client-Id"
    ),
):

    rate = check_rate_limit(x_client_id)
    if rate:
        return rate

    if idempotency_key is None:
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Idempotency-Key required"
            }
        )

    if idempotency_key in idempotency_store:
        response.status_code = 200
        return idempotency_store[idempotency_key]

    new_order = {
        "id": str(uuid.uuid4()),
        "item": order.item
    }

    idempotency_store[idempotency_key] = new_order

    return new_order


# -----------------------------
# List Orders
# -----------------------------
@app.get("/orders")
def list_orders(
    limit: int = Query(
        default=10,
        gt=0
    ),
    cursor: Optional[str] = None,
    x_client_id: str = Header(
        ...,
        alias="X-Client-Id"
    ),
):

    rate = check_rate_limit(x_client_id)
    if rate:
        return rate

    start = 0

    if cursor:
        try:
            start = int(cursor)
        except ValueError:
            start = 0

    end = min(start + limit, TOTAL_ORDERS)

    items = catalog[start:end]

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = str(end)

    return {
        "items": items,
        "next_cursor": next_cursor
    }
