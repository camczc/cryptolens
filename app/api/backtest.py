"""app/api/backtest.py"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.session import get_db
from app.services.backtester import (
    BacktestEngine, CompositeScoreStrategy, RSIMeanReversionStrategy,
    GoldenCrossStrategy, FearGreedStrategy
)
from app.models.schemas import BacktestRequest, BacktestResponse, EquityCurvePoint

router = APIRouter()

STRATEGY_MAP = {
    "composite": CompositeScoreStrategy,
    "rsi": RSIMeanReversionStrategy,
    "golden_cross": GoldenCrossStrategy,
    "fear_greed": FearGreedStrategy,
}

def result_to_response(result, backtest_id=None):
    return BacktestResponse(
        coin=result.coin,
        symbol=result.symbol,
        strategy_name=result.strategy_name,
        strategy_params=result.strategy_params,
        start_date=result.start_date,
        end_date=result.end_date,
        initial_capital=result.initial_capital,
        total_return=result.total_return,
        annualized_return=result.annualized_return,
        benchmark_return=result.benchmark_return,
        alpha=result.total_return - result.benchmark_return,
        sharpe_ratio=result.sharpe_ratio,
        sortino_ratio=result.sortino_ratio,
        calmar_ratio=result.calmar_ratio,
        max_drawdown=result.max_drawdown,
        volatility_annualized=result.volatility_annualized,
        win_rate=result.win_rate,
        total_trades=result.total_trades,
        avg_trade_duration_days=result.avg_trade_duration_days,
        equity_curve=[EquityCurvePoint(**p) for p in result.equity_curve],
        trade_log=result.trade_log,
        backtest_id=backtest_id,
    )

@router.post("", response_model=BacktestResponse)
def run_backtest(body: BacktestRequest, db: Session = Depends(get_db)):
    if body.strategy not in STRATEGY_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown strategy. Choose from: {list(STRATEGY_MAP.keys())}")
    strategy = STRATEGY_MAP[body.strategy]()
    engine = BacktestEngine(db)
    try:
        result = engine.run(
            coingecko_id=body.coingecko_id.lower(),
            strategy=strategy,
            start_date=body.start_date,
            end_date=body.end_date,
            initial_capital=body.initial_capital,
            commission=body.commission,
            slippage=body.slippage,
        )
        return result_to_response(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")

@router.post("/compare", response_model=list[BacktestResponse])
def compare_strategies(
    coingecko_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = 10_000.0,
    db: Session = Depends(get_db),
):
    from datetime import date as date_type
    start = date_type.fromisoformat(start_date) if start_date else date_type(2022, 1, 1)
    end = date_type.fromisoformat(end_date) if end_date else date_type.today()
    engine = BacktestEngine(db)
    results = []
    for strategy_cls in STRATEGY_MAP.values():
        try:
            result = engine.run(coingecko_id.lower(), strategy_cls(), start, end, initial_capital)
            results.append(result_to_response(result))
        except Exception:
            continue
    if not results:
        raise HTTPException(status_code=500, detail="All strategies failed")
    results.sort(key=lambda r: r.sharpe_ratio, reverse=True)
    return results
