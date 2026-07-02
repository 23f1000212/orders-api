from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import time
from typing import Optional
import base64

app = FastAPI()

# Task requirement: Allow cross-origin requests from the browser for verification
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Assigned Values
TOTAL_ORDERS = 59
RATE_LIMIT_R = 17
RATE_LIMIT_WINDOW = 10  # seconds

# Data Stores (In-memory)
orders_catalog = [{"id": i, "description": f"Order {i} details"} for i in range(1, TOTAL_ORDERS + 1)]
idempotency_cache = {}
client_requests = {}

@app.middleware("http")
async def per_client_rate_limiter(request: Request, call_next):
    if request.url.path == "/orders":
        client_id = request.headers.get("X-Client-Id")
        if client_id:
            now = time.time()
            timestamps = client_requests.get(client_id, [])
            
            # Sliding window filter
            timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
            
            if len(timestamps) >= RATE_LIMIT_R:
                return Response(status_code=429, headers={"Retry-After": str(RATE_LIMIT_WINDOW)})
            
            timestamps.append(now)
            client_requests[client_id] = timestamps
            
    return await call_next(request)

@app.post("/orders", status_code=201)
def create_order(idempotency_key: str = Header(..., alias="Idempotency-Key")):
    # 1. Idempotent Order Creation
    if idempotency_key in idempotency_cache:
        return idempotency_cache[idempotency_key]
    
    # Generate new order and cache against the key
    new_order = {"id": f"ord_{len(idempotency_cache) + 1}", "status": "created"}
    idempotency_cache[idempotency_key] = new_order
    return new_order

@app.get("/orders")
def get_orders(limit: int = 10, cursor: Optional[str] = None):
    # 2. Cursor Pagination
    start_idx = 0
    if cursor:
        try:
            # Decode opaque cursor back to index integer
            start_idx = int(base64.b64decode(cursor).decode('utf-8'))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor format")
            
    end_idx = start_idx + limit
    items = orders_catalog[start_idx:end_idx]
    
    next_cursor = None
    if end_idx < len(orders_catalog):
        # Encode next index as opaque cursor
        next_cursor = base64.b64encode(str(end_idx).encode('utf-8')).decode('utf-8')
        
    return {"items": items, "next_cursor": next_cursor}
