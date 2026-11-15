"""Serialize provenance insertion and dependency changes."""
from pathlib import Path
from alembic import op

revision = "0008_provenance_lock"
down_revision = "0007_signal_provenance"
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).resolve().parents[2] / "migrations" / "0008_provenance_lock.sql").read_text(encoding="utf-8"))


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
