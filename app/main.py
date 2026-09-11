from fastapi import FastAPI
from app.routers import auth

app = FastAPI(title="Orbitdesk API")

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(auth.router)
