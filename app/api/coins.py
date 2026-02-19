"""app/api/coins.py"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Coin
from app.services.ingestion import IngestionService
from app.models.schemas import CoinResponse

router = APIRouter()

@router.get("", response_model=list[CoinResponse])
def list_coins(db: Session = Depends(get_db)):
    return db.query(Coin).filter(Coin.is_active == True).all()

@router.post("/{coingecko_id}", response_model=CoinResponse)
def add_coin(coingecko_id: str, db: Session = Depends(get_db)):
    svc = IngestionService(db)
    try:
        coin = svc.get_or_create_coin(coingecko_id.lower())
        return coin
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{coingecko_id}/seed")
def seed_coin(coingecko_id: str, days: int = 365, db: Session = Depends(get_db)):
    svc = IngestionService(db)
    try:
        rows = svc.fetch_price_history(coingecko_id.lower(), days=days)
        return {"coin": coingecko_id, "rows_upserted": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
