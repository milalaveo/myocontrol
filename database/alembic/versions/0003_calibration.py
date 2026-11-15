"""Add gestures, labelled repetitions and calibration subsets."""

from pathlib import Path

from alembic import op

revision = "0003_calibration"
down_revision = "0002_split"
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).resolve().parents[2] / "migrations" / "0003_calibration.sql").read_text(encoding="utf-8")
    op.execute(sql)


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
