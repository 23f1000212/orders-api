from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import time
import uuid

app = FastAPI()

# ----------------------------
# CORS
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://exam.sanand.workers.dev"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 59
RATE_LIMIT = 17
WINDOW = 10

# Stores
idempotency = {}
rate_limits = {}


class Order(BaseModel):
    product: str = ""
    quantity: int = 1


# ----------------------------
# Middleware
# ----------------------------
@app.middleware("http")
async def limiter(request: Request, call_next):

    if request.url.path == "/orders":

        client = request.headers.get("X-Client-Id","default")

        now = time.time()

        history = rate_limits.get(client, [])

        history = [x for x in history if now-x < 10]

        if len(history) >= 17:
            return Response(
                status_code=429,
                headers={
                    "Retry-After":"10"
                }
            )

        history.append(now)

        rate_limits[client]=history

    return await call_next(request)


# ----------------------------
# POST /orders
# ----------------------------
@app.post("/orders", status_code=201)
async def create_order(request: Request, body: Order):

    key = request.headers.get("Idempotency-Key")

    if key and key in idempotency:
        return idempotency[key]

    result = {
        "id": str(uuid.uuid4()),
        "product": body.product,
        "quantity": body.quantity
    }

    if key:
        idempotency[key] = result

    return JSONResponse(
        status_code=201,
        content=result
    )


# ----------------------------
# GET /orders
# ----------------------------
@app.get("/orders")
async def get_orders(limit: int = 10, cursor: str | None = None):

    try:
        start = int(cursor) if cursor else 0
    except:
        start = 0

    start = max(0, start)

    end = min(start + limit, TOTAL_ORDERS)

    items = []

    for i in range(start + 1, end + 1):
        items.append({"id": i})

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = str(end)

    return {
        "items": items,
        "next_cursor": next_cursor
    }


@app.get("/")
async def root():
    return {
        "status": "running"
    }
