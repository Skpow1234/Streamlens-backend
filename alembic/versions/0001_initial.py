"""initial tables

Revision ID: 0001_initial
Revises: 
Create Date: 2025-08-10 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlmodel import SQLModel

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Let SQLModel metadata create tables (including Timescale) if using autogenerate in future.
    # Here we keep it minimal and rely on subsequent migrations for changes.
    pass


def downgrade() -> None:
    pass


