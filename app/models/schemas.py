"""
app/models/schemas.py
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class CoinBase(BaseModel):
    coingecko_id: str
    symbol: str
    name: Optional[str] = None


class CoinResponse(CoinBase):
    id: int
    market_cap_rank: Optional[int] = None
    is_active: bool = True

    class Config:
        from_attributes = True


class SignalResponse(BaseModel):
    coin: str
    symbol: Optional[str] = None
    price_usd: float
    price_change_7d_pct: Optional[float] = None
    signal: str
    composite_score: float
    indicators: dict


class BacktestRequest(BaseModel):
    coingecko_id: str
    strategy: str = "composite"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    initial_capital: float = 10_000.0
    commission: float = 0.001
    slippage: float = 0.001
    save: bool = False


class EquityCurvePoint(BaseModel):
    date: str
    value: float
    benchmark_value: float


class BacktestResponse(BaseModel):
    coin: str
    symbol: str
    strategy_name: str
    strategy_params: dict
    start_date: date
    end_date: date
    initial_capital: float
    total_return: float
    annualized_return: float
    benchmark_return: float
    alpha: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    volatility_annualized: float
    win_rate: float
    total_trades: int
    avg_trade_duration_days: float
    equity_curve: List[EquityCurvePoint]
    trade_log: List[dict]
    backtest_id: Optional[int] = None


class ResearchRequest(BaseModel):
    coingecko_id: str
    question: Optional[str] = None


class ResearchResponse(BaseModel):
    coin: str
    symbol: Optional[str] = None
    price_usd: float
    signal: str
    composite_score: float
    brief: str
    generated_at: str
    indicators: dict


class HealthResponse(BaseModel):
    status: str
    env: str
