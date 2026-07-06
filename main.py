from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uuid
import time

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

TOTAL_ORDERS = 59
RATE_LIMIT = 17
WINDOW_SECONDS = 10

# In-memory stores
idempotency_store = {}
rate_limit_store = {}


class OrderRequest(BaseModel):
    product: str = ""
    quantity: int = 1


# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders", status_code=201)
async def create_order(request: Request, order: OrderRequest):

    client_id = request.headers.get("X-Client-Id", "anonymous")
    idem_key = request.headers.get("Idempotency-Key")

    # -----------------------------
    # Rate Limiting
    # -----------------------------
    now = time.time()

    timestamps = rate_limit_store.get(client_id, [])

    timestamps = [
        t for t in timestamps
        if now - t < WINDOW_SECONDS
    ]

    if len(timestamps) >= RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            headers={
                "Retry-After": str(WINDOW_SECONDS)
            },
            content={
                "detail": "Rate limit exceeded"
            }
        )

    timestamps.append(now)
    rate_limit_store[client_id] = timestamps

    # -----------------------------
    # Idempotency
    # -----------------------------
    if idem_key and idem_key in idempotency_store:
        return idempotency_store[idem_key]

    order_data = {
        "id": str(uuid.uuid4()),
        "product": order.product,
        "quantity": order.quantity
    }

    if idem_key:
        idempotency_store[idem_key] = order_data

    return JSONResponse(
        status_code=201,
        content=order_data
    )


# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
async def get_orders(
    limit: int = 10,
    cursor: str | None = None
):

    start = int(cursor) if cursor else 0

    end = min(start + limit, TOTAL_ORDERS)

    items = []

    for i in range(start + 1, end + 1):
        items.append({
            "id": i
        })

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = str(end)

    return {
        "items": items,
        "next_cursor": next_cursor
    }


# -----------------------------
# Health Check
# -----------------------------
@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "Orders API is running"
    }
