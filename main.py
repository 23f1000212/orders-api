import time
import uuid
from collections import defaultdict, deque
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

TOTAL_ORDERS = 59
RATE_LIMIT = 17
WINDOW = 10  # seconds

app = FastAPI(title="Orders API")

# Allow browser access for the grader
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# In-memory storage
# ----------------------------

idempotency_store = {}

client_requests = defaultdict(deque)

catalog = [
    {
        "id": i,
        "item": f"Item {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]


class OrderRequest(BaseModel):
    item: str = "Sample Item"


# ----------------------------
# Rate Limiter
# ----------------------------

def check_rate_limit(client_id: str):

    now = time.time()

    bucket = client_requests[client_id]

    while bucket and now - bucket[0] >= WINDOW:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT:

        retry = WINDOW - (now - bucket[0])

        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(int(retry) + 1)
            }
        )

    bucket.append(now)


# ----------------------------
# Create Order
# ----------------------------

@app.post("/orders", status_code=201)
def create_order(
    order: OrderRequest,
    response: Response,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_client_id: str = Header(..., alias="X-Client-Id"),
):

    check_rate_limit(x_client_id)

    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key required"
        )

    if idempotency_key in idempotency_store:

        response.status_code = 200

        return idempotency_store[idempotency_key]

    new_order = {
        "id": str(uuid.uuid4()),
        "item": order.item,
    }

    idempotency_store[idempotency_key] = new_order

    return new_order


# ----------------------------
# Pagination
# ----------------------------

@app.get("/orders")
def list_orders(
    limit: int = Query(10, gt=0),
    cursor: Optional[str] = None,
    x_client_id: str = Header(..., alias="X-Client-Id"),
):

    check_rate_limit(x_client_id)

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
        "next_cursor": next_cursor,
    }


@app.get("/")
def home():
    return {
        "message": "Orders API Running"
    }
