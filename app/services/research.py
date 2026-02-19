"""
app/services/research.py

Claude-powered crypto research briefs.
"""
import logging
from datetime import datetime
from typing import Optional

import anthropic
from sqlalchemy.orm import Session

from app.services.signals import SignalEngine
from app.services.ingestion import IngestionService
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ResearchService:

    def __init__(self, db: Session):
        self.db = db
        self.signal_engine = SignalEngine(db)
        self.ingestion = IngestionService(db)
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def generate_brief(self, coingecko_id: str, question: Optional[str] = None) -> dict:
        """Generate a Claude-powered research brief for a coin."""
        summary = self.signal_engine.get_signal_summary(coingecko_id)
        prices = self.ingestion.get_price_dataframe(coingecko_id)

        # Build price context
        current_price = float(prices["close"].iloc[-1])
        price_30d_ago = float(prices["close"].iloc[-30]) if len(prices) >= 30 else current_price
        price_change_30d = (current_price / price_30d_ago - 1) * 100
        all_time_high = float(prices["close"].max())
        drawdown_from_ath = (current_price / all_time_high - 1) * 100

        indicators = summary["indicators"]
        coin_name = coingecko_id.replace("-", " ").title()
        symbol = summary.get("symbol", coingecko_id.upper())

        prompt = f"""You are a senior crypto analyst writing a concise research brief.

## {coin_name} ({symbol}) — Signal Data as of {datetime.now().strftime('%Y-%m-%d')}

**Price:** ${current_price:,.4f}
**30-Day Change:** {price_change_30d:+.1f}%
**7-Day Change:** {summary.get('price_change_7d_pct', 0):+.1f}%
**Drawdown from ATH (in dataset):** {drawdown_from_ath:.1f}%

**Technical Signals:**
- RSI-14: {indicators.get('rsi_14', 'N/A'):.1f} → {indicators.get('rsi_interpretation', 'N/A')}
- MACD Histogram: {indicators.get('macd_hist', 0):.4f} → {indicators.get('macd_interpretation', 'N/A')}
- Bollinger %B: {indicators.get('bb_pct', 0.5):.2f} → {indicators.get('bb_interpretation', 'N/A')}

**Crypto-Specific:**
- Fear & Greed Index: {indicators.get('fear_greed_index', 'N/A')} ({indicators.get('fear_greed_label', 'N/A')})
- 24h Volume Change: {f"{indicators.get('volume_change_24h', 0):.1f}%" if indicators.get('volume_change_24h') else 'N/A'}

**Composite Signal Score:** {summary.get('composite_score', 0):+.3f} → **{summary.get('signal', 'NEUTRAL')}**
(Scale: -1.0 = strong sell, 0 = neutral, +1.0 = strong buy)

{"**Analyst Question:** " + question if question else ""}

Write a structured research brief with these sections:
1. **Signal Summary** (2-3 sentences on what the data says)
2. **Bull Case** (2-3 bullet points)
3. **Bear Case** (2-3 bullet points)
4. **Key Levels to Watch** (support/resistance based on Bollinger Bands and moving averages)
5. **Bottom Line** (1-2 sentence conclusion)

Be direct, data-driven, and specific. Avoid generic crypto hype. Note that past signals do not guarantee future performance."""

        response = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        brief_text = response.content[0].text

        return {
            "coin": coingecko_id,
            "symbol": symbol,
            "price_usd": current_price,
            "signal": summary.get("signal"),
            "composite_score": summary.get("composite_score"),
            "brief": brief_text,
            "generated_at": datetime.utcnow().isoformat(),
            "indicators": indicators,
        }
