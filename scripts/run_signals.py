"""
scripts/run_signals.py

Usage:
    python scripts/run_signals.py --coin bitcoin ethereum
"""
import sys, os, argparse
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.services.signals import SignalEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coin", nargs="+", required=True)
    args = parser.parse_args()

    db = SessionLocal()
    engine = SignalEngine(db)

    for coin_id in args.coin:
        print(f"\nComputing signals for {coin_id}...")
        try:
            rows = engine.compute_and_store(coin_id.lower())
            summary = engine.get_signal_summary(coin_id.lower())
            score = summary["composite_score"]
            signal = summary["signal"]
            price = summary["price_usd"]
            ind = summary["indicators"]
            print(f"  Stored {rows} rows")
            print(f"  {'='*50}")
            print(f"  {coin_id.upper()}  |  ${price:,.2f}  |  {signal}")
            print(f"  Composite Score: {score:+.3f}")
            print(f"  RSI-14: {ind.get('rsi_14', 'N/A'):.1f}  |  Fear & Greed: {ind.get('fear_greed_index', 'N/A')} ({ind.get('fear_greed_label', 'N/A')})")
            print(f"  {'='*50}")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    db.close()


if __name__ == "__main__":
    main()
