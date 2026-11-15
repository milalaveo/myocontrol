"""Expose completed metrics without artifact storage metadata."""
from pathlib import Path
from alembic import op

revision = "0015_reviewer_view"
down_revision = "0014_recovery"
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).resolve().parents[2] / "migrations" / "0015_reviewer_view.sql").read_text(encoding="utf-8"))


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
