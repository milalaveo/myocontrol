"""Add canonical signals and draft split manifests."""

from pathlib import Path

from alembic import op

revision = "0002_split"
down_revision = "0001_sources"
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).resolve().parents[2] / "migrations" / "0002_split.sql").read_text(encoding="utf-8")
    op.execute(sql)


def downgrade():
    raise NotImplementedError("Restore a backup or create a forward migration; automatic downgrade is unsupported.")
