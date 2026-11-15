"""Serialize snapshots with gesture and feature configuration edits."""
from pathlib import Path
from alembic import op

revision = "0016_snapshot_locks"
down_revision = "0015_reviewer_view"
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).resolve().parents[2] / "migrations" / "0016_snapshot_locks.sql").read_text(encoding="utf-8"))


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
