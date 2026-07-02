import base64
import time
from collections import defaultdict
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Constants
# -----------------------------
TOTAL_ORDERS = 59
RATE_LIMIT = 17
WINDOW = 10

# -----------------------------
# Data
# -----------------------------
orders_catalog = [
    {
        "id": i,
        "description": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

idempotency_cache = {}

client_requests = defaultdict(list)


# -----------------------------
# Rate Limiter
# -----------------------------
def rate_limit(client_id: str):

    now = time.time()

    timestamps = client_requests[client_id]

    timestamps = [
        t
        for t in timestamps
        if now - t < WINDOW
    ]

    client_requests[client_id] = timestamps

    if len(timestamps) >= RATE_LIMIT:

        retry_after = max(
            1,
            int(WINDOW - (now - timestamps[0])) + 1
        )

        response = JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded"
            }
        )

        response.headers["Retry-After"] = str(retry_after)

        return response

    timestamps.append(now)

    client_requests[client_id] = timestamps

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
# POST /orders
# -----------------------------
@app.post("/orders", status_code=201)
def create_order(
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    x_client_id: str = Header("default", alias="X-Client-Id"),
):

    limit = rate_limit(x_client_id)

    if limit:
        return limit

    if idempotency_key in idempotency_cache:

        response.status_code = 200

        return idempotency_cache[idempotency_key]

    order = {
        "id": f"ord_{len(idempotency_cache)+1}"
    }

    idempotency_cache[idempotency_key] = order

    return order


# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def get_orders(
    limit: int = 10,
    cursor: Optional[str] = None,
    x_client_id: str = Header("default", alias="X-Client-Id"),
):

    rl = rate_limit(x_client_id)

    if rl:
        return rl

    if limit <= 0:
        raise HTTPException(
            status_code=400,
            detail="limit must be greater than zero"
        )

    start = 0

    if cursor:

        try:

            start = int(
                base64.b64decode(cursor).decode()
            )

        except Exception:

            raise HTTPException(
                status_code=400,
                detail="Invalid cursor"
            )

    end = min(start + limit, TOTAL_ORDERS)

    items = orders_catalog[start:end]

    next_cursor = None

    if end < TOTAL_ORDERS:

        next_cursor = base64.b64encode(
            str(end).encode()
        ).decode()

    return {
        "items": items,
        "next_cursor": next_cursor
    }
