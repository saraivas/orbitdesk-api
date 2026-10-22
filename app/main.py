import redis
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from app.routers import auth, tasks

app = FastAPI(title="Orbitdesk API")


@app.exception_handler(redis.RedisError)
def redis_unavailable(request: Request, exc: redis.RedisError):
    # Sessions live in Redis: without it a session cannot be proven valid, so
    # authentication fails closed (ADR 0003).
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Service temporarily unavailable"},
    )


@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(auth.router)
app.include_router(tasks.router)
