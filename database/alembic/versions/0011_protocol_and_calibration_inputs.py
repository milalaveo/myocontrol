"""Version protocols and record exact calibration inputs."""
from pathlib import Path
from alembic import op

revision = "0011_protocol_calibration"
down_revision = "0010_result_integrity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute((Path(__file__).resolve().parents[2] / "migrations" / "0011_protocol_and_calibration_inputs.sql").read_text(encoding="utf-8"))


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
