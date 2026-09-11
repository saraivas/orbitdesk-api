from fastapi import FastAPI
from app.routers import auth, tasks

app = FastAPI(title="Orbitdesk API")

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(auth.router)
app.include_router(tasks.router)
