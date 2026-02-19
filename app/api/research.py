"""app/api/research.py"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.session import get_db
from app.services.research import ResearchService
from app.models.schemas import ResearchResponse

router = APIRouter()

@router.get("/{coingecko_id}", response_model=ResearchResponse)
def get_research(
    coingecko_id: str,
    question: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    svc = ResearchService(db)
    try:
        return svc.generate_brief(coingecko_id.lower(), question=question)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Research failed: {e}")
