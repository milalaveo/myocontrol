"""Create initial source and recording provenance tables."""

from pathlib import Path

from alembic import op

revision = "0001_sources"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).resolve().parents[2] / "migrations" / "0001_sources.sql").read_text(encoding="utf-8")
    op.execute(sql)


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
