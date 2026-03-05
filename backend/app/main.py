from fastapi import FastAPI
from app.api.router import api_router

from sqlalchemy import text

from app.db.session import engine
app = FastAPI(title="Esports Analytics API")

app.include_router(api_router)

from fastapi.middleware.cors import CORSMiddleware
from app.core.settings import settings  # adjust

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # list[str]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/db-test")
def db_test():
    with engine.connect() as conn:
        return {"result": conn.execute(text("SELECT 1")).scalar()}