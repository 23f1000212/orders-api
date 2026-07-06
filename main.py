from fastapi import FastAPI, Request, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import time

app = FastAPI()

# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with exam origin if required
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 59
RATE_LIMIT = 17
WINDOW = 10  # seconds

# -----------------------------
# In-memory stores
# -----------------------------
idempotency_store = {}
rate_limit_store = {}


class OrderRequest(BaseModel):
    item: Optional[str] = None
    quantity: Optional[int] = 1


@app.post("/orders", status_code=201)
async def create_order(
    request: OrderRequest,
    response: Response,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    client_id: Optional[str] = Header("default", alias="X-Client-Id"),
):

    now = time.time()

    timestamps = rate_limit_store.get(client_id, [])
    timestamps = [t for t in timestamps if now - t < WINDOW]

    if len(timestamps) >= RATE_LIMIT:
        response.headers["Retry-After"] = str(WINDOW)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    timestamps.append(now)
    rate_limit_store[client_id] = timestamps

    if idempotency_key:
        if idempotency_key in idempotency_store:
            return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4()),
        "item": request.item,
        "quantity": request.quantity,
    }

    if idempotency_key:
        idempotency_store[idempotency_key] = order

    return order


@app.get("/orders")
async def list_orders(limit: int = 10, cursor: Optional[str] = None):

    start = int(cursor) if cursor else 0

    end = min(start + limit, TOTAL_ORDERS)

    items = [{"id": i} for i in range(start + 1, end + 1)]

    next_cursor = str(end) if end < TOTAL_ORDERS else None

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
