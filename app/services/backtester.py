"""
app/services/backtester.py

Backtesting engine for crypto strategies.
Benchmark: Bitcoin (BTC) buy-and-hold.
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.services.ingestion import IngestionService
from app.services.signals import SignalEngine

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 365  # crypto trades 24/7
RISK_FREE_RATE = 0.045


@dataclass
class BacktestResult:
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
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    volatility_annualized: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    avg_trade_duration_days: float = 0.0
    equity_curve: list = field(default_factory=list)
    trade_log: list = field(default_factory=list)


# ------------------------------------------------------------------
# Strategy definitions
# ------------------------------------------------------------------

class CompositeScoreStrategy:
    name = "composite"
    params = {"buy_threshold": 0.15, "sell_threshold": -0.15}

    def generate_signals(self, prices: pd.DataFrame, signals: pd.DataFrame) -> pd.Series:
        score = signals["composite_score"].reindex(prices.index).fillna(0)
        position = pd.Series(0, index=prices.index)
        position[score > self.params["buy_threshold"]] = 1
        position[score < self.params["sell_threshold"]] = 0
        return position.ffill().fillna(0)


class RSIMeanReversionStrategy:
    name = "rsi_mean_reversion"
    params = {"oversold": 30, "overbought": 70}

    def generate_signals(self, prices: pd.DataFrame, signals: pd.DataFrame) -> pd.Series:
        rsi = signals["rsi_14"].reindex(prices.index).fillna(50)
        position = pd.Series(0, index=prices.index)
        in_position = False
        for i in range(len(rsi)):
            if not in_position and rsi.iloc[i] < self.params["oversold"]:
                in_position = True
            elif in_position and rsi.iloc[i] > self.params["overbought"]:
                in_position = False
            position.iloc[i] = 1 if in_position else 0
        return position


class GoldenCrossStrategy:
    name = "golden_cross"
    params = {"fast": 50, "slow": 200}

    def generate_signals(self, prices: pd.DataFrame, signals: pd.DataFrame) -> pd.Series:
        sma50 = signals["sma_50"].reindex(prices.index)
        sma200 = signals["sma_200"].reindex(prices.index)
        position = (sma50 > sma200).astype(float).fillna(0)
        return position


class FearGreedStrategy:
    name = "fear_greed_contrarian"
    params = {"extreme_fear_buy": 25, "extreme_greed_sell": 75}

    def generate_signals(self, prices: pd.DataFrame, signals: pd.DataFrame) -> pd.Series:
        fg = signals["fear_greed_index"].reindex(prices.index).fillna(50)
        position = pd.Series(0, index=prices.index)
        in_position = False
        for i in range(len(fg)):
            if not in_position and fg.iloc[i] < self.params["extreme_fear_buy"]:
                in_position = True
            elif in_position and fg.iloc[i] > self.params["extreme_greed_sell"]:
                in_position = False
            position.iloc[i] = 1 if in_position else 0
        return position


# ------------------------------------------------------------------
# Backtest Engine
# ------------------------------------------------------------------

class BacktestEngine:

    def __init__(self, db: Session):
        self.db = db
        self.ingestion = IngestionService(db)
        self.signal_engine = SignalEngine(db)

    def run(
        self,
        coingecko_id: str,
        strategy,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        initial_capital: float = 10_000.0,
        commission: float = 0.001,
        slippage: float = 0.001,
    ) -> BacktestResult:

        from app.db.models import Coin
        coin = self.db.query(Coin).filter(Coin.coingecko_id == coingecko_id.lower()).first()
        symbol = coin.symbol if coin else coingecko_id.upper()

        prices = self.ingestion.get_price_dataframe(coingecko_id, start_date, end_date)
        signals_df = self.signal_engine._compute_all_signals(
            prices, self.ingestion.fetch_fear_greed(limit=len(prices) + 10)
        )

        common_idx = prices.index.intersection(signals_df.index)
        prices = prices.loc[common_idx]
        signals_df = signals_df.loc[common_idx]

        if start_date:
            prices = prices[prices.index.date >= start_date]
            signals_df = signals_df[signals_df.index >= pd.Timestamp(start_date)]
        if end_date:
            prices = prices[prices.index.date <= end_date]
            signals_df = signals_df[signals_df.index <= pd.Timestamp(end_date)]

        if len(prices) < 30:
            raise ValueError(f"Not enough data: {len(prices)} rows")

        raw_signals = strategy.generate_signals(prices, signals_df)
        portfolio = self._simulate_portfolio(prices, raw_signals, initial_capital, commission, slippage)
        benchmark_returns = self._get_benchmark_returns(coingecko_id, prices.index[0].date(), prices.index[-1].date())

        return self._compute_metrics(
            coin=coingecko_id,
            symbol=symbol,
            strategy=strategy,
            portfolio=portfolio,
            benchmark_returns=benchmark_returns,
            initial_capital=initial_capital,
            start_date=prices.index[0].date(),
            end_date=prices.index[-1].date(),
        )

    def _simulate_portfolio(self, prices, signals, initial_capital, commission, slippage):
        close = prices["close"]
        signals = signals.reindex(close.index).fillna(0)
        position_changes = signals.diff().fillna(signals)
        entries = position_changes > 0
        exits = position_changes < 0
        asset_returns = close.pct_change().fillna(0)
        cost = (commission + slippage) * (entries | exits).astype(float)
        strategy_returns = signals.shift(1).fillna(0) * asset_returns - cost
        portfolio_value = initial_capital * (1 + strategy_returns).cumprod()

        return pd.DataFrame({
            "close": close,
            "position": signals,
            "asset_return": asset_returns,
            "strategy_return": strategy_returns,
            "portfolio_value": portfolio_value,
            "is_entry": entries,
            "is_exit": exits,
        })

    def _build_trade_log(self, portfolio):
        trades = []
        entry_date = entry_price = None
        for idx, row in portfolio.iterrows():
            if row["is_entry"] and entry_date is None:
                entry_date, entry_price = idx, row["close"]
            elif row["is_exit"] and entry_date is not None:
                trade_return = (row["close"] - entry_price) / entry_price
                trades.append({
                    "entry_date": str(entry_date.date()),
                    "exit_date": str(idx.date()),
                    "entry_price": round(float(entry_price), 6),
                    "exit_price": round(float(row["close"]), 6),
                    "return": round(float(trade_return), 6),
                    "duration_days": (idx - entry_date).days,
                    "profitable": trade_return > 0,
                })
                entry_date = entry_price = None

        # Close any still-open position at end of data
        if entry_date is not None:
            last_idx = portfolio.index[-1]
            last_price = float(portfolio["close"].iloc[-1])
            trade_return = (last_price - entry_price) / entry_price
            trades.append({
                "entry_date": str(entry_date.date()),
                "exit_date": str(last_idx.date()),
                "entry_price": round(float(entry_price), 6),
                "exit_price": round(float(last_price), 6),
                "return": round(float(trade_return), 6),
                "duration_days": (last_idx - entry_date).days,
                "profitable": trade_return > 0,
            })
        return trades

    def _get_benchmark_returns(self, coingecko_id, start, end):
        """BTC buy-and-hold as benchmark (or same coin if already BTC)."""
        try:
            bench_id = "bitcoin" if coingecko_id != "bitcoin" else "ethereum"
            bench_prices = self.ingestion.get_price_dataframe(bench_id, start, end)
            returns = bench_prices["close"].pct_change().fillna(0)
            returns.index = pd.to_datetime(returns.index)
            return returns
        except Exception as e:
            logger.warning(f"Could not get benchmark: {e}")
            return pd.Series(dtype=float)

    def _compute_metrics(self, coin, symbol, strategy, portfolio, benchmark_returns, initial_capital, start_date, end_date):
        pv = portfolio["portfolio_value"]
        daily_returns = portfolio["strategy_return"]
        trades = self._build_trade_log(portfolio)

        total_return = float((pv.iloc[-1] / initial_capital) - 1)
        n_years = len(pv) / TRADING_DAYS_PER_YEAR
        annualized_return = float((1 + total_return) ** (1 / n_years) - 1) if n_years > 0 else 0.0
        vol = float(daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))

        excess = daily_returns - (RISK_FREE_RATE / TRADING_DAYS_PER_YEAR)
        sharpe = float(excess.mean() / daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)) if daily_returns.std() > 0 else 0.0

        downside = daily_returns[daily_returns < 0]
        downside_std = float(downside.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
        sortino = float((annualized_return - RISK_FREE_RATE) / downside_std) if downside_std > 0 else 0.0

        rolling_max = pv.cummax()
        drawdown = (pv - rolling_max) / rolling_max
        max_drawdown = float(drawdown.min())
        calmar = float(annualized_return / abs(max_drawdown)) if max_drawdown != 0 else 0.0

        aligned_bench = benchmark_returns.reindex(pv.index).fillna(0)
        benchmark_total = float((1 + aligned_bench).prod() - 1)

        bench_cumulative = initial_capital * (1 + aligned_bench).cumprod()
        equity_curve = [{
            "date": str(idx.date()),
            "value": round(float(v), 2),
            "benchmark_value": round(float(bench_cumulative.get(idx, initial_capital)), 2),
        } for idx, v in pv.items()]

        win_rate = float(sum(1 for t in trades if t["profitable"]) / len(trades)) if trades else 0.0
        avg_duration = float(np.mean([t["duration_days"] for t in trades])) if trades else 0.0

        return BacktestResult(
            coin=coin,
            symbol=symbol,
            strategy_name=strategy.name,
            strategy_params=strategy.params,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            total_return=total_return,
            annualized_return=annualized_return,
            benchmark_return=benchmark_total,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_drawdown,
            volatility_annualized=vol,
            win_rate=win_rate,
            total_trades=len(trades),
            avg_trade_duration_days=avg_duration,
            equity_curve=equity_curve,
            trade_log=trades,
        )
