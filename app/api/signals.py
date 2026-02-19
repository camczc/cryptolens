"""app/api/signals.py"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.signals import SignalEngine
from app.models.schemas import SignalResponse

router = APIRouter()

@router.get("/{coingecko_id}", response_model=SignalResponse)
def get_signals(coingecko_id: str, db: Session = Depends(get_db)):
    engine = SignalEngine(db)
    try:
        return engine.get_signal_summary(coingecko_id.lower())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing signals: {e}")

@router.post("/{coingecko_id}/compute")
def compute_signals(coingecko_id: str, db: Session = Depends(get_db)):
    engine = SignalEngine(db)
    try:
        rows = engine.compute_and_store(coingecko_id.lower())
        return {"coin": coingecko_id, "rows_stored": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
