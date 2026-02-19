"""
app/services/ingestion.py

Fetches crypto price data from CoinGecko API (free tier, no key needed).
Also fetches Fear & Greed index from alternative.me.
"""
import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional

import requests
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Coin, CoinPrice
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

COINGECKO_BASE = settings.coingecko_api_url
FEAR_GREED_URL = settings.fear_greed_url


class IngestionService:

    def __init__(self, db: Session):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "CryptoLens/1.0",
        })
        if settings.coingecko_api_key:
            self.session.headers["x-cg-pro-api-key"] = settings.coingecko_api_key

    # ------------------------------------------------------------------
    # Coin management
    # ------------------------------------------------------------------

    def get_or_create_coin(self, coingecko_id: str) -> Coin:
        """Get or create a coin record."""
        coin = self.db.query(Coin).filter(Coin.coingecko_id == coingecko_id.lower()).first()
        if coin:
            return coin

        # Fetch metadata from CoinGecko
        try:
            resp = self.session.get(
                f"{COINGECKO_BASE}/coins/{coingecko_id}",
                params={"localization": False, "tickers": False, "community_data": False},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            coin = Coin(
                coingecko_id=coingecko_id.lower(),
                symbol=data.get("symbol", "").upper(),
                name=data.get("name", coingecko_id),
                market_cap_rank=data.get("market_cap_rank"),
            )
        except Exception as e:
            logger.warning(f"Could not fetch metadata for {coingecko_id}: {e}")
            coin = Coin(
                coingecko_id=coingecko_id.lower(),
                symbol=coingecko_id.upper()[:10],
                name=coingecko_id,
            )

        self.db.add(coin)
        self.db.commit()
        self.db.refresh(coin)
        logger.info(f"Created coin: {coin.symbol} ({coingecko_id})")
        return coin

    # ------------------------------------------------------------------
    # Price ingestion
    # ------------------------------------------------------------------

    def fetch_price_history(
        self,
        coingecko_id: str,
        days: int = 365,
        vs_currency: str = "usd",
    ) -> int:
        """
        Fetch OHLCV history from CoinGecko and store in DB.
        Returns number of rows upserted.
        """
        coin = self.get_or_create_coin(coingecko_id)

        logger.info(f"Fetching {days}d price history for {coingecko_id}")

        try:
            # CoinGecko OHLC endpoint (returns [timestamp, open, high, low, close])
            resp = self.session.get(
                f"{COINGECKO_BASE}/coins/{coingecko_id}/ohlc",
                params={"vs_currency": vs_currency, "days": days},
                timeout=30,
            )
            resp.raise_for_status()
            ohlc_data = resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch OHLC for {coingecko_id}: {e}")
            raise

        # Also fetch market chart for volume + market cap
        try:
            resp2 = self.session.get(
                f"{COINGECKO_BASE}/coins/{coingecko_id}/market_chart",
                params={"vs_currency": vs_currency, "days": days, "interval": "daily"},
                timeout=30,
            )
            resp2.raise_for_status()
            chart_data = resp2.json()
        except Exception as e:
            logger.warning(f"Could not fetch market chart for {coingecko_id}: {e}")
            chart_data = {}

        # Build DataFrames
        ohlc_df = pd.DataFrame(ohlc_data, columns=["timestamp", "open", "high", "low", "close"])
        ohlc_df["date"] = pd.to_datetime(ohlc_df["timestamp"], unit="ms").dt.date

        # Volume
        vol_df = pd.DataFrame(
            chart_data.get("total_volumes", []), columns=["timestamp", "volume"]
        )
        if not vol_df.empty:
            vol_df["date"] = pd.to_datetime(vol_df["timestamp"], unit="ms").dt.date
            vol_df = vol_df.groupby("date")["volume"].last().reset_index()

        # Market cap
        mcap_df = pd.DataFrame(
            chart_data.get("market_caps", []), columns=["timestamp", "market_cap"]
        )
        if not mcap_df.empty:
            mcap_df["date"] = pd.to_datetime(mcap_df["timestamp"], unit="ms").dt.date
            mcap_df = mcap_df.groupby("date")["market_cap"].last().reset_index()

        # Merge
        df = ohlc_df.groupby("date").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
        ).reset_index()

        if not vol_df.empty:
            df = df.merge(vol_df, on="date", how="left")
        else:
            df["volume"] = None

        if not mcap_df.empty:
            df = df.merge(mcap_df, on="date", how="left")
        else:
            df["market_cap"] = None

        # Upsert
        rows_upserted = 0
        for _, row in df.iterrows():
            stmt = insert(CoinPrice).values(
                coin_id=coin.id,
                date=row["date"],
                open=float(row["open"]) if pd.notna(row.get("open")) else None,
                high=float(row["high"]) if pd.notna(row.get("high")) else None,
                low=float(row["low"]) if pd.notna(row.get("low")) else None,
                close=float(row["close"]),
                volume=float(row["volume"]) if pd.notna(row.get("volume")) else None,
                market_cap=float(row["market_cap"]) if pd.notna(row.get("market_cap")) else None,
            ).on_conflict_do_update(
                constraint="uq_cl_price_coin_date",
                set_={
                    "open": float(row["open"]) if pd.notna(row.get("open")) else None,
                    "high": float(row["high"]) if pd.notna(row.get("high")) else None,
                    "low": float(row["low"]) if pd.notna(row.get("low")) else None,
                    "close": float(row["close"]),
                    "volume": float(row["volume"]) if pd.notna(row.get("volume")) else None,
                    "market_cap": float(row["market_cap"]) if pd.notna(row.get("market_cap")) else None,
                }
            )
            self.db.execute(stmt)
            rows_upserted += 1

        self.db.commit()
        logger.info(f"Upserted {rows_upserted} rows for {coingecko_id}")
        return rows_upserted

    def get_price_dataframe(
        self,
        coingecko_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Load price data from DB as DataFrame."""
        coin = self.db.query(Coin).filter(Coin.coingecko_id == coingecko_id.lower()).first()
        if not coin:
            raise ValueError(f"Coin {coingecko_id} not found. Seed it first.")

        query = self.db.query(CoinPrice).filter(CoinPrice.coin_id == coin.id)
        if start_date:
            query = query.filter(CoinPrice.date >= start_date)
        if end_date:
            query = query.filter(CoinPrice.date <= end_date)

        rows = query.order_by(CoinPrice.date.asc()).all()
        if not rows:
            raise ValueError(f"No price data for {coingecko_id}. Run fetch_price_history() first.")

        df = pd.DataFrame([{
            "date": r.date,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
            "market_cap": r.market_cap,
        } for r in rows])

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df

    # ------------------------------------------------------------------
    # Fear & Greed index
    # ------------------------------------------------------------------

    def fetch_fear_greed(self, limit: int = 365) -> pd.DataFrame:
        """
        Fetch Fear & Greed index history from alternative.me.
        Returns DataFrame with date, value (0-100), label columns.
        """
        try:
            resp = self.session.get(
                FEAR_GREED_URL,
                params={"limit": limit, "format": "json"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            df = pd.DataFrame(data)
            df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s").dt.date
            df["value"] = df["value"].astype(float)
            df = df.rename(columns={"value_classification": "label"})
            return df[["date", "value", "label"]].sort_values("date")
        except Exception as e:
            logger.warning(f"Could not fetch Fear & Greed: {e}")
            return pd.DataFrame(columns=["date", "value", "label"])

    # ------------------------------------------------------------------
    # Top coins list
    # ------------------------------------------------------------------

    def fetch_top_coins(self, limit: int = 50) -> list:
        """Fetch top N coins by market cap from CoinGecko."""
        try:
            resp = self.session.get(
                f"{COINGECKO_BASE}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": limit,
                    "page": 1,
                    "sparkline": False,
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Could not fetch top coins: {e}")
            return []
