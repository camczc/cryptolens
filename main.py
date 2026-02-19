"""
CryptoLens — AI-Powered Crypto Research Platform
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.models.schemas import HealthResponse

logging.basicConfig(level=logging.INFO)
settings = get_settings()

app = FastAPI(
    title="CryptoLens API",
    description="AI-powered crypto research with quantitative signals",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api import coins, signals, backtest, research

app.include_router(coins.router, prefix="/coins", tags=["Coins"])
app.include_router(signals.router, prefix="/signals", tags=["Signals"])
app.include_router(backtest.router, prefix="/backtest", tags=["Backtest"])
app.include_router(research.router, prefix="/analyze", tags=["Research"])


@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="ok", env=settings.env)
