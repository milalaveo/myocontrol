"""Record worker heartbeats, recover stale runs and scope retry keys."""
from pathlib import Path
from alembic import op

revision = "0014_recovery"
down_revision = "0013_evaluation_integrity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).resolve().parents[2] / "migrations" / "0014_recovery.sql").read_text(encoding="utf-8"))


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
