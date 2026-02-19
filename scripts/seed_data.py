"""
scripts/seed_data.py

Usage:
    python scripts/seed_data.py --coin bitcoin ethereum solana
    python scripts/seed_data.py --coin bitcoin --days 730
"""
import sys, os, argparse, time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal, init_db
from app.services.ingestion import IngestionService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coin", nargs="+", required=True)
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    svc = IngestionService(db)

    for i, coin_id in enumerate(args.coin):
        if i > 0:
            print("  Waiting 8s to avoid rate limiting...")
            time.sleep(8)
        print(f"\nSeeding {coin_id}...")
        try:
            rows = svc.fetch_price_history(coin_id.lower(), days=args.days)
            print(f"  ✓ {rows} rows inserted for {coin_id}")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    db.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
