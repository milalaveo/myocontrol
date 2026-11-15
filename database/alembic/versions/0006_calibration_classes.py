"""Require a gesture set and class counts when freezing calibration."""
from pathlib import Path
from alembic import op

revision = "0006_calibration_classes"
down_revision = "0005_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).resolve().parents[2] / "migrations" / "0006_calibration_classes.sql").read_text(encoding="utf-8"))


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
