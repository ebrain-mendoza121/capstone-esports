"""clarify_players_region_stores_routing

Revision ID: f0a6ca7bbdf5
Revises: e22f3c14ba64
Create Date: 2026-02-24 14:56:41.748795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0a6ca7bbdf5'
down_revision: Union[str, Sequence[str], None] = 'e22f3c14ba64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Clarify that players.region stores routing values.
    
    This migration:
    1. Adds a comment to the region column
    2. Normalizes any existing region values to routing format
    
    Valid routing values: americas, europe, asia, sea
    """
    # Add comment to clarify what region stores
    op.execute("""
        COMMENT ON COLUMN players.region IS 'Regional routing: americas, europe, asia, sea'
    """)
    
    # Normalize existing data to routing format (if any exists)
    # Map common platform values to routing
    op.execute("""
        UPDATE players
        SET region = CASE
            WHEN UPPER(region) IN ('NA', 'BR', 'LAN', 'LAS', 'AMERICAS') THEN 'americas'
            WHEN UPPER(region) IN ('KR', 'JP', 'ASIA') THEN 'asia'
            WHEN UPPER(region) IN ('EUNE', 'EUW', 'ME1', 'TR', 'RU', 'EUROPE') THEN 'europe'
            WHEN UPPER(region) IN ('OCE', 'SG2', 'TW2', 'VN2', 'SEA') THEN 'sea'
            ELSE LOWER(region)  -- Keep as-is if already lowercase routing
        END
        WHERE region IS NOT NULL
    """)


def downgrade() -> None:
    """
    Downgrade schema.
    
    Note: This removes the comment but doesn't reverse data normalization
    as the original values are lost.
    """
    op.execute("""
        COMMENT ON COLUMN players.region IS NULL
    """)
