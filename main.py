import base64
import time
from collections import defaultdict
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Orders API")

# -------------------------------------------------------
# CORS
# -------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------
# Constants
# -------------------------------------------------------
TOTAL_ORDERS = 59
RATE_LIMIT = 17
WINDOW = 10

# -------------------------------------------------------
# In-memory storage
# -------------------------------------------------------
orders = [
    {
        "id": i,
        "description": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

idempotency = {}

client_hits = defaultdict(list)


# -------------------------------------------------------
# Rate Limiter
# -------------------------------------------------------
def check_rate_limit(client_id: str):

    now = time.time()

    hits = client_hits[client_id]

    hits = [
        t
        for t in hits
        if now - t < WINDOW
    ]

    client_hits[client_id] = hits

    if len(hits) >= RATE_LIMIT:

        retry_after = max(
            1,
            int(WINDOW - (now - hits[0])) + 1
        )

        response = Response(
            content='{"detail":"Rate limit exceeded"}',
            media_type="application/json",
            status_code=429
        )

        response.headers["Retry-After"] = str(retry_after)

        return response

    hits.append(now)

    client_hits[client_id] = hits

    return None


# -------------------------------------------------------
# Home
# -------------------------------------------------------
@app.get("/")
def root():

    return {
        "message": "Orders API Running"
    }


# -------------------------------------------------------
# POST /orders
# -------------------------------------------------------
@app.post("/orders")
def create_order(
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    x_client_id: str = Header("default", alias="X-Client-Id"),
):

    rl = check_rate_limit(x_client_id)

    if rl is not None:
        return rl

    if idempotency_key in idempotency:

        response.status_code = 200

        return idempotency[idempotency_key]

    order = {
        "id": f"ord_{len(idempotency)+1}"
    }

    idempotency[idempotency_key] = order

    response.status_code = 201

    return order


# -------------------------------------------------------
# GET /orders
# -------------------------------------------------------
@app.get("/orders")
def get_orders(
    limit: int = 10,
    cursor: Optional[str] = None,
    x_client_id: str = Header("default", alias="X-Client-Id"),
):

    rl = check_rate_limit(x_client_id)

    if rl is not None:
        return rl

    if limit <= 0:

        raise HTTPException(
            status_code=400,
            detail="Invalid limit"
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
