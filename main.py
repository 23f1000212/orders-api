import time
import uuid
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import redis

# --- Configuration Values ---
TOTAL_ORDERS = 59
RATE_LIMIT_MAX_REQS = 17
RATE_LIMIT_WINDOW_SEC = 10

app = FastAPI()

# --- 1. CORS Setup ---
# Allows the exam portal's browser client to verify requests directly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"] # Crucial for exposing the 429 header to the browser
)

# Connect to local Redis (ensure Redis server is running)
redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

# --- Rate Limiting Logic (Sliding Window) ---
def is_rate_limited(client_id: str) -> bool:
    key = f"ratelimit:{client_id}"
    now = time.time()
    
    # Use a Redis pipeline for atomic operations
    pipe = redis_client.pipeline()
    # 1. Remove timestamps older than the 10-second window
    pipe.zremrangebyscore(key, 0, now - RATE_LIMIT_WINDOW_SEC)
    # 2. Add the current request timestamp
    pipe.zadd(key, {str(now): now})
    # 3. Count the number of requests currently in the window
    pipe.zcard(key)
    # 4. Set an expiry on the key to prevent memory leaks
    pipe.expire(key, RATE_LIMIT_WINDOW_SEC + 2)
    
    res = pipe.execute()
    request_count = res[2]
    
    return request_count > RATE_LIMIT_MAX_REQS

# --- Middleware to Intercept /orders for Rate Limiting ---
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Only apply rate limiting to the /orders endpoint
    if request.url.path == "/orders":
        client_id = request.headers.get("X-Client-Id", "default")
        if is_rate_limited(client_id):
            return Response(
                status_code=429, 
                headers={"Retry-After": str(RATE_LIMIT_WINDOW_SEC)}
            )
    return await call_next(request)

# --- 2. Idempotent Order Creation ---
@app.post("/orders")
async def create_order(request: Request):
    idem_key = request.headers.get("Idempotency-Key")
    
    # If the key exists, check Redis for a cached response
    if idem_key:
        cached_id = redis_client.get(f"idem:{idem_key}")
        if cached_id:
            return {"id": cached_id}

    # Generate a new unique order ID
    order_id = str(uuid.uuid4())
    
    # Cache the generated ID against the idempotency key for future identical requests
    if idem_key:
        # Cache expires in 1 hour (3600 seconds)
        redis_client.setex(f"idem:{idem_key}", 3600, order_id)

    return JSONResponse(status_code=201, content={"id": order_id})

# --- 3. Cursor Pagination ---
@app.get("/orders")
async def get_orders(limit: int = 10, cursor: str = None):
    # Generate the fixed catalog of orders from 1 to TOTAL_ORDERS
    all_items = [{"id": i} for i in range(1, TOTAL_ORDERS + 1)]
    
    # Determine the starting index. If no cursor is provided, start at 0.
    start_idx = int(cursor) if cursor and cursor.isdigit() else 0
    end_idx = start_idx + limit
    
    # Slice the list to get the current page
    page = all_items[start_idx:end_idx]
    
    # Calculate the next cursor. If we've reached the end, return None.
    next_cur = str(end_idx) if end_idx < len(all_items) else None
    
    return {"items": page, "next_cursor": next_cur}
