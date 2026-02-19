"""
app/services/signals.py

Computes technical + crypto-specific signals for a given coin.
"""
import logging
from datetime import date, datetime
from typing import Optional

import pandas as pd
import numpy as np
import ta
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Coin, CoinSignal
from app.services.ingestion import IngestionService
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SignalEngine:

    def __init__(self, db: Session):
        self.db = db
        self.ingestion = IngestionService(db)

    def compute_and_store(self, coingecko_id: str) -> int:
        """Compute all signals and store in DB. Returns rows written."""
        coin = self.db.query(Coin).filter(Coin.coingecko_id == coingecko_id.lower()).first()
        if not coin:
            raise ValueError(f"Coin {coingecko_id} not found")

        prices = self.ingestion.get_price_dataframe(coingecko_id)
        fear_greed = self.ingestion.fetch_fear_greed(limit=len(prices) + 10)

        signals_df = self._compute_all_signals(prices, fear_greed)

        rows_written = 0
        for idx, row in signals_df.iterrows():
            row_date = idx.date() if hasattr(idx, 'date') else idx

            def safe(val):
                if val is None:
                    return None
                try:
                    v = float(val)
                    return None if np.isnan(v) or np.isinf(v) else v
                except:
                    return None

            stmt = insert(CoinSignal).values(
                coin_id=coin.id,
                date=row_date,
                rsi_14=safe(row.get("rsi_14")),
                macd=safe(row.get("macd")),
                macd_signal=safe(row.get("macd_signal")),
                macd_hist=safe(row.get("macd_hist")),
                bb_upper=safe(row.get("bb_upper")),
                bb_lower=safe(row.get("bb_lower")),
                bb_pct=safe(row.get("bb_pct")),
                sma_20=safe(row.get("sma_20")),
                sma_50=safe(row.get("sma_50")),
                sma_200=safe(row.get("sma_200")),
                ema_12=safe(row.get("ema_12")),
                ema_26=safe(row.get("ema_26")),
                obv=safe(row.get("obv")),
                fear_greed_index=safe(row.get("fear_greed_index")),
                fear_greed_label=str(row.get("fear_greed_label", "")) or None,
                volume_change_24h=safe(row.get("volume_change_24h")),
                market_cap_change_24h=safe(row.get("market_cap_change_24h")),
                composite_score=safe(row.get("composite_score")),
                computed_at=datetime.utcnow(),
            ).on_conflict_do_update(
                constraint="uq_cl_signal_coin_date",
                set_={
                    "rsi_14": safe(row.get("rsi_14")),
                    "macd_hist": safe(row.get("macd_hist")),
                    "bb_pct": safe(row.get("bb_pct")),
                    "fear_greed_index": safe(row.get("fear_greed_index")),
                    "fear_greed_label": str(row.get("fear_greed_label", "")) or None,
                    "composite_score": safe(row.get("composite_score")),
                    "computed_at": datetime.utcnow(),
                }
            )
            self.db.execute(stmt)
            rows_written += 1

        self.db.commit()
        logger.info(f"Stored {rows_written} signal rows for {coingecko_id}")
        return rows_written

    def _compute_all_signals(
        self,
        prices: pd.DataFrame,
        fear_greed: pd.DataFrame,
    ) -> pd.DataFrame:
        """Compute all signals from price DataFrame."""
        close = prices["close"]
        volume = prices.get("volume", pd.Series(dtype=float))
        market_cap = prices.get("market_cap", pd.Series(dtype=float))

        signals = pd.DataFrame(index=prices.index)

        # --- RSI ---
        signals["rsi_14"] = ta.momentum.RSIIndicator(close=close, window=14).rsi()

        # --- MACD ---
        macd = ta.trend.MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        signals["macd"] = macd.macd()
        signals["macd_signal"] = macd.macd_signal()
        signals["macd_hist"] = macd.macd_diff()

        # --- Bollinger Bands ---
        bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
        signals["bb_upper"] = bb.bollinger_hband()
        signals["bb_lower"] = bb.bollinger_lband()
        signals["bb_pct"] = bb.bollinger_pband()

        # --- Moving Averages ---
        signals["sma_20"] = ta.trend.SMAIndicator(close=close, window=20).sma_indicator()
        signals["sma_50"] = ta.trend.SMAIndicator(close=close, window=50).sma_indicator()
        signals["sma_200"] = ta.trend.SMAIndicator(close=close, window=200).sma_indicator()
        signals["ema_12"] = ta.trend.EMAIndicator(close=close, window=12).ema_indicator()
        signals["ema_26"] = ta.trend.EMAIndicator(close=close, window=26).ema_indicator()

        # --- OBV ---
        if volume is not None and not volume.isna().all():
            signals["obv"] = ta.volume.OnBalanceVolumeIndicator(
                close=close, volume=volume.fillna(0)
            ).on_balance_volume()

        # --- Volume change ---
        if volume is not None and not volume.isna().all():
            signals["volume_change_24h"] = volume.pct_change() * 100

        # --- Market cap change ---
        if market_cap is not None and not market_cap.isna().all():
            signals["market_cap_change_24h"] = market_cap.pct_change() * 100

        # --- Fear & Greed ---
        if not fear_greed.empty:
            fg = fear_greed.copy()
            fg["date"] = pd.to_datetime(fg["date"])
            fg = fg.set_index("date")
            signals["fear_greed_index"] = fg["value"].reindex(signals.index, method="ffill")
            signals["fear_greed_label"] = fg["label"].reindex(signals.index, method="ffill")

        # --- Composite Score (-1 to +1) ---
        signals["composite_score"] = self._compute_composite(signals)

        return signals

    def _compute_composite(self, df: pd.DataFrame) -> pd.Series:
        """Weighted composite score from all signals."""
        score = pd.Series(0.0, index=df.index)
        weights = 0.0

        # RSI (weight: 0.25)
        if "rsi_14" in df:
            rsi_score = df["rsi_14"].apply(lambda x:
                -1.0 if x > 70 else
                +1.0 if x < 30 else
                (50 - x) / 50 * 0.5
            )
            score += rsi_score * 0.25
            weights += 0.25

        # MACD histogram (weight: 0.25)
        if "macd_hist" in df:
            macd_norm = df["macd_hist"].fillna(0)
            max_val = macd_norm.abs().rolling(50, min_periods=1).max().replace(0, 1)
            score += (macd_norm / max_val).clip(-1, 1) * 0.25
            weights += 0.25

        # Bollinger %B (weight: 0.20)
        if "bb_pct" in df:
            bb_score = df["bb_pct"].apply(lambda x:
                -1.0 if x > 0.9 else
                +1.0 if x < 0.1 else
                (0.5 - x)
            )
            score += bb_score * 0.20
            weights += 0.20

        # Trend: price vs SMA50 (weight: 0.15)
        if "sma_50" in df and "close" not in df.columns:
            pass
        elif "sma_50" in df:
            pass  # SMA trend added below when close is available

        # Fear & Greed (weight: 0.15) — contrarian
        if "fear_greed_index" in df:
            fg_score = df["fear_greed_index"].apply(lambda x:
                +1.0 if x < 20 else   # extreme fear = buy
                -1.0 if x > 80 else   # extreme greed = sell
                (50 - x) / 50 * 0.5
            )
            score += fg_score * 0.15
            weights += 0.15

        return (score / weights if weights > 0 else score).clip(-1, 1)

    def get_latest_signals(self, coingecko_id: str, n: int = 1) -> pd.DataFrame:
        """Get most recent N signal rows from DB."""
        coin = self.db.query(Coin).filter(Coin.coingecko_id == coingecko_id.lower()).first()
        if not coin:
            raise ValueError(f"Coin {coingecko_id} not found")

        rows = (
            self.db.query(CoinSignal)
            .filter(CoinSignal.coin_id == coin.id)
            .order_by(CoinSignal.date.desc())
            .limit(n)
            .all()
        )

        return pd.DataFrame([{
            "date": r.date,
            "rsi_14": r.rsi_14,
            "macd": r.macd,
            "macd_signal": r.macd_signal,
            "macd_hist": r.macd_hist,
            "bb_upper": r.bb_upper,
            "bb_lower": r.bb_lower,
            "bb_pct": r.bb_pct,
            "sma_20": r.sma_20,
            "sma_50": r.sma_50,
            "sma_200": r.sma_200,
            "fear_greed_index": r.fear_greed_index,
            "fear_greed_label": r.fear_greed_label,
            "volume_change_24h": r.volume_change_24h,
            "composite_score": r.composite_score,
        } for r in rows])

    def get_signal_summary(self, coingecko_id: str) -> dict:
        """Get human-readable signal summary for a coin."""
        df = self.get_latest_signals(coingecko_id, n=1)
        if df.empty:
            raise ValueError(f"No signals for {coingecko_id}. Run compute_and_store() first.")

        row = df.iloc[0]
        prices = self.ingestion.get_price_dataframe(coingecko_id)
        current_price = float(prices["close"].iloc[-1])
        price_change_7d = float(
            (prices["close"].iloc[-1] / prices["close"].iloc[-7] - 1) * 100
        ) if len(prices) >= 7 else 0.0

        rsi = row["rsi_14"]
        score = row["composite_score"]
        fg = row["fear_greed_index"]

        overall = (
            "STRONG BUY" if score > 0.5 else
            "BUY" if score > 0.15 else
            "NEUTRAL" if score > -0.15 else
            "SELL" if score > -0.5 else
            "STRONG SELL"
        )

        return {
            "coin": coingecko_id,
            "price_usd": current_price,
            "price_change_7d_pct": price_change_7d,
            "signal": overall,
            "composite_score": float(score) if score is not None else 0.0,
            "indicators": {
                "rsi_14": float(rsi) if rsi else None,
                "rsi_interpretation": (
                    "oversold (bullish)" if rsi and rsi < 30 else
                    "overbought (bearish)" if rsi and rsi > 70 else
                    "neutral"
                ),
                "macd_hist": float(row["macd_hist"]) if row["macd_hist"] else None,
                "macd_interpretation": (
                    "bullish" if row["macd_hist"] and row["macd_hist"] > 0 else "bearish"
                ),
                "bb_pct": float(row["bb_pct"]) if row["bb_pct"] else None,
                "bb_interpretation": (
                    "near lower band (potential bounce)" if row["bb_pct"] and row["bb_pct"] < 0.2 else
                    "near upper band (potential reversal)" if row["bb_pct"] and row["bb_pct"] > 0.8 else
                    "mid-range"
                ),
                "fear_greed_index": float(fg) if fg else None,
                "fear_greed_label": row["fear_greed_label"],
                "volume_change_24h": float(row["volume_change_24h"]) if row["volume_change_24h"] else None,
            }
        }
