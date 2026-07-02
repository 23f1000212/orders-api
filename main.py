import time
import uuid
from collections import defaultdict, deque
from typing import Optional

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

TOTAL_ORDERS = 59
RATE_LIMIT = 17
WINDOW = 10  # seconds

app = FastAPI(title="Orders API")

# -----------------------------------
# CORS
# -----------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------
# In-memory storage
# -----------------------------------
idempotency_store = {}

client_requests = defaultdict(deque)

catalog = [
    {
        "id": i,
        "item": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]


# -----------------------------------
# Rate Limiter
# -----------------------------------
def check_rate_limit(client_id: str):
    now = time.time()
    bucket = client_requests[client_id]

    while bucket and now - bucket[0] >= WINDOW:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT:
        retry_after = max(
            1,
            int(bucket[0] + WINDOW - now + 0.999)
        )

        response = JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"}
        )

        response.headers["Retry-After"] = str(retry_after)

        return response

    bucket.append(now)
    return None


# -----------------------------------
# Home
# -----------------------------------
@app.get("/")
def home():
    return {
        "message": "Orders API Running"
    }


# -----------------------------------
# POST /orders
# -----------------------------------
@app.post("/orders", status_code=201)
async def create_order(
    request: Request,
    response: Response,
    idempotency_key: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key"
    ),
    x_client_id: Optional[str] = Header(
        default="default",
        alias="X-Client-Id"
    ),
):

    rate = check_rate_limit(x_client_id)
    if rate is not None:
        return rate

    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Idempotency-Key required"
            }
        )

    if idempotency_key in idempotency_store:
        response.status_code = 200
        return idempotency_store[idempotency_key]

    try:
        body = await request.json()
    except Exception:
        body = {}

    if not isinstance(body, dict):
        body = {}

    order = {
        "id": str(uuid.uuid4())
    }

    order.update(body)

    idempotency_store[idempotency_key] = order

    return order


# -----------------------------------
# GET /orders
# -----------------------------------
@app.get("/orders")
def list_orders(
    limit: int = Query(10, gt=0),
    cursor: Optional[str] = None,
    x_client_id: Optional[str] = Header(
        default="default",
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
