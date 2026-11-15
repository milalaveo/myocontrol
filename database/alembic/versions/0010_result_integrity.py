"""Protect published results and validate model input roles."""
from pathlib import Path
from alembic import op

revision = "0010_result_integrity"
down_revision = "0009_publication"
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).resolve().parents[2] / "migrations" / "0010_result_integrity.sql").read_text(encoding="utf-8"))


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
