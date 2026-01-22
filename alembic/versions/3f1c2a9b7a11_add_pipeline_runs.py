from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "3f1c2a9b7a11"
down_revision = "d25a81caa961"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_kind", sa.String(length=64), nullable=False),
        sa.Column("digest_date", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_pipeline_runs_user_kind_day", "pipeline_runs", ["user_id", "run_kind", "digest_date"])
    op.create_index("ix_pipeline_runs_user_started_at", "pipeline_runs", ["user_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_user_started_at", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_user_kind_day", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
