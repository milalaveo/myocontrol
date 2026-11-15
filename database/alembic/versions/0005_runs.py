"""Add initial run, model and evaluation tables."""

from pathlib import Path
from alembic import op

revision = "0005_runs"
down_revision = "0004_integrity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).resolve().parents[2] / "migrations" / "0005_runs.sql").read_text(encoding="utf-8"))


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
