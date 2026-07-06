import base64
import time
from collections import defaultdict
from typing import Optional

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Orders API")

# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# Constants
# --------------------------------------------------

TOTAL_ORDERS = 59
RATE_LIMIT = 17
WINDOW = 10

# --------------------------------------------------
# Data
# --------------------------------------------------

orders = [
    {
        "id": i,
        "description": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

idempotency_cache = {}

client_requests = defaultdict(list)

# --------------------------------------------------
# Rate Limiter
# --------------------------------------------------

def rate_limit(client_id: str):

    now = time.time()

    hits = [
        t for t in client_requests[client_id]
        if now - t < WINDOW
    ]

    client_requests[client_id] = hits

    if len(hits) >= RATE_LIMIT:

        retry_after = max(
            1,
            int(WINDOW - (now - hits[0])) + 1
        )

        return JSONResponse(
            status_code=429,
            headers={
                "Retry-After": str(retry_after)
            },
            content={
                "detail": "Rate limit exceeded"
            },
        )

    hits.append(now)

    client_requests[client_id] = hits

    return None


# --------------------------------------------------
# Home
# --------------------------------------------------

@app.get("/")
def home():

    return {
        "message": "Orders API Running"
    }


# --------------------------------------------------
# POST /orders
# --------------------------------------------------

@app.post("/orders")
async def create_order(
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_client_id: str = Header("default", alias="X-Client-Id"),
):

    limited = rate_limit(x_client_id)

    if limited:
        return limited

    if not idempotency_key:

        idempotency_key = f"generated-{time.time_ns()}"

    if idempotency_key in idempotency_cache:

        return JSONResponse(
            status_code=200,
            content=idempotency_cache[idempotency_key],
        )

    order = {
        "id": f"ord_{len(idempotency_cache)+1}"
    }

    idempotency_cache[idempotency_key] = order

    return JSONResponse(
        status_code=201,
        content=order,
    )


# --------------------------------------------------
# GET /orders
# --------------------------------------------------

@app.get("/orders")
async def list_orders(
    limit: int = 10,
    cursor: Optional[str] = None,
    x_client_id: str = Header("default", alias="X-Client-Id"),
):

    limited = rate_limit(x_client_id)

    if limited:
        return limited

    if limit < 1:
        limit = 1

    start = 0

    if cursor:

        try:
            start = int(
                base64.b64decode(cursor).decode()
            )

        except Exception:

            start = 0

    end = min(start + limit, TOTAL_ORDERS)

    items = orders[start:end]

    next_cursor = None

    if end < TOTAL_ORDERS:

        next_cursor = base64.b64encode(
            str(end).encode()
        ).decode()

    return {
        "items": items,
        "next_cursor": next_cursor
    }
