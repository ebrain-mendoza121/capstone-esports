from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.db.session import get_db
from app.models.player import Player


class PlayerResponse(BaseModel):
    id: int
    riot_id: str
    tag_line: str
    puuid: str
    region: str
    created_at: datetime
    
    class Config:
        from_attributes = True


router = APIRouter(prefix="/players", tags=["players"])


@router.get("/", response_model=List[PlayerResponse])
def list_players(db: Session = Depends(get_db)):
    """Get all players in the database."""
    players = db.query(Player).all()
    return players


@router.get("/{puuid}", response_model=PlayerResponse)
def get_player(puuid: str, db: Session = Depends(get_db)):
    """Get a specific player by PUUID."""
    player = db.query(Player).filter(Player.puuid == puuid).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player
