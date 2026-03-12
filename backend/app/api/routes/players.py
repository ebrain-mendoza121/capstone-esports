from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.player import Player

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/")
def list_players(db: Session = Depends(get_db)):
    return db.query(Player).all()


@router.get("/{puuid}")
def get_player(puuid: str, db: Session = Depends(get_db)):
    return db.query(Player).filter(Player.puuid == puuid).first()
