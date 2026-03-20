from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class Platform(str, Enum):
    """League of Legends platform regions."""
    NA = "NA"
    BR = "BR"
    LAN = "LAN"
    LAS = "LAS"
    KR = "KR"
    JP = "JP"
    EUNE = "EUNE"
    EUW = "EUW"
    ME1 = "ME1"
    TR = "TR"
    RU = "RU"
    OCE = "OCE"
    SG2 = "SG2"
    TW2 = "TW2"
    VN2 = "VN2"


# Platform to routing mapping for Riot API
PLATFORM_TO_ROUTING = {
    Platform.NA: "americas",
    Platform.BR: "americas",
    Platform.LAN: "americas",
    Platform.LAS: "americas",
    Platform.KR: "asia",
    Platform.JP: "asia",
    Platform.EUNE: "europe",
    Platform.EUW: "europe",
    Platform.ME1: "europe",
    Platform.TR: "europe",
    Platform.RU: "europe",
    Platform.OCE: "sea",
    Platform.SG2: "sea",
    Platform.TW2: "sea",
    Platform.VN2: "sea",
}


class IngestPlayerRequest(BaseModel):
    gameName: str = Field(..., min_length=1, description="Riot ID game name")
    tagLine: str = Field(..., min_length=1, description="Riot ID tag line")
    platform: str = Field(..., description="Platform region (NA, EUW, KR, etc.)")
    count: int = Field(default=20, ge=1, le=100, description="Number of matches to fetch (max 100)")
    queue: int = Field(default=420, description="Queue ID filter (420=Ranked Solo, 440=Ranked Flex)")
    fetch_timeline: bool = Field(default=False, description="Also fetch & store match timeline data (slower, uses extra API quota)")

    @field_validator("platform", mode="before")
    @classmethod
    def normalize_platform(cls, v: str) -> str:
        """Normalize platform to uppercase and validate."""
        if not isinstance(v, str):
            raise ValueError("platform must be a string")
        
        normalized = v.upper().strip()
        
        try:
            Platform(normalized)
        except ValueError:
            valid_platforms = ", ".join([p.value for p in Platform])
            raise ValueError(
                f"Invalid platform '{v}'. Must be one of: {valid_platforms}"
            )
        
        return normalized


class IngestPlayerResponse(BaseModel):
    puuid: str
    platform: str
    routing: str
    inserted: int
    skipped: int
    failed: List[str]


class BatchIngestPlayerResult(BaseModel):
    """Result for a single player in a batch ingestion request."""
    gameName: str
    tagLine: str
    platform: str
    status: str          # "success" | "partial" | "error"
    puuid: Optional[str] = None
    inserted: int = 0
    skipped: int = 0
    failed: List[str] = []
    error: Optional[str] = None


class BatchIngestResponse(BaseModel):
    total: int
    succeeded: int
    errored: int
    results: List[BatchIngestPlayerResult]
