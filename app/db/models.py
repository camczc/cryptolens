"""
app/db/models.py
"""
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime,
    Boolean, ForeignKey, UniqueConstraint, JSON, Text
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Coin(Base):
    __tablename__ = "cl_coins"

    id = Column(Integer, primary_key=True)
    coingecko_id = Column(String(100), unique=True, nullable=False)  # e.g. "bitcoin"
    symbol = Column(String(20), nullable=False)                       # e.g. "BTC"
    name = Column(String(100))                                        # e.g. "Bitcoin"
    market_cap_rank = Column(Integer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    prices = relationship("CoinPrice", back_populates="coin", cascade="all, delete-orphan")
    signals = relationship("CoinSignal", back_populates="coin", cascade="all, delete-orphan")


class CoinPrice(Base):
    __tablename__ = "cl_coin_prices"
    __table_args__ = (
        UniqueConstraint("coin_id", "date", name="uq_cl_price_coin_date"),
    )

    id = Column(Integer, primary_key=True)
    coin_id = Column(Integer, ForeignKey("cl_coins.id"), nullable=False)
    date = Column(Date, nullable=False)

    # OHLCV
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float, nullable=False)
    volume = Column(Float)

    # Market data
    market_cap = Column(Float)
    total_volume_usd = Column(Float)

    coin = relationship("Coin", back_populates="prices")


class CoinSignal(Base):
    __tablename__ = "cl_coin_signals"
    __table_args__ = (
        UniqueConstraint("coin_id", "date", name="uq_cl_signal_coin_date"),
    )

    id = Column(Integer, primary_key=True)
    coin_id = Column(Integer, ForeignKey("cl_coins.id"), nullable=False)
    date = Column(Date, nullable=False)

    # Technical signals
    rsi_14 = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    macd_hist = Column(Float)
    bb_upper = Column(Float)
    bb_lower = Column(Float)
    bb_pct = Column(Float)
    sma_20 = Column(Float)
    sma_50 = Column(Float)
    sma_200 = Column(Float)
    ema_12 = Column(Float)
    ema_26 = Column(Float)
    obv = Column(Float)

    # Crypto-specific signals
    fear_greed_index = Column(Float)       # 0-100
    fear_greed_label = Column(String(50))  # "Extreme Fear", "Greed", etc.
    volume_change_24h = Column(Float)      # % change in volume
    market_cap_change_24h = Column(Float)  # % change in market cap

    # Composite score
    composite_score = Column(Float)        # -1 to +1

    computed_at = Column(DateTime, default=datetime.utcnow)

    coin = relationship("Coin", back_populates="signals")


class BacktestRun(Base):
    __tablename__ = "cl_backtest_runs"

    id = Column(Integer, primary_key=True)
    coin_id = Column(String(100), nullable=False)   # coingecko_id
    coin_symbol = Column(String(20))
    strategy_name = Column(String(100))
    strategy_params = Column(JSON, default={})
    start_date = Column(Date)
    end_date = Column(Date)
    total_return = Column(Float)
    annualized_return = Column(Float)
    benchmark_return = Column(Float)
    sharpe_ratio = Column(Float)
    sortino_ratio = Column(Float)
    max_drawdown = Column(Float)
    win_rate = Column(Float)
    total_trades = Column(Integer)
    avg_trade_duration_days = Column(Float)
    equity_curve = Column(JSON, default=[])
    trade_log = Column(JSON, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)
