"""Bind signal provenance and sampling rates to frozen split checksums."""
from pathlib import Path
from alembic import op

revision = "0007_signal_provenance"
down_revision = "0006_calibration_classes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).resolve().parents[2] / "migrations" / "0007_signal_provenance.sql").read_text(encoding="utf-8"))


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
