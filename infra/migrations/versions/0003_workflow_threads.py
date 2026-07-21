"""Add workflow lineage and resumable run input."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_workflow_threads"
down_revision: str | None = "0002_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stage_runs", sa.Column("workflow_thread_id", sa.String(36)))
    op.add_column("stage_runs", sa.Column("parent_stage_run_id", sa.String(36)))
    op.add_column(
        "stage_runs",
        sa.Column("input_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.execute("UPDATE stage_runs SET workflow_thread_id = id")
    op.alter_column("stage_runs", "workflow_thread_id", nullable=False)
    op.create_foreign_key(
        "fk_stage_runs_parent",
        "stage_runs",
        "stage_runs",
        ["parent_stage_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_stage_runs_workflow_thread_id",
        "stage_runs",
        ["workflow_thread_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stage_runs_workflow_thread_id", table_name="stage_runs")
    op.drop_constraint("fk_stage_runs_parent", "stage_runs", type_="foreignkey")
    op.drop_column("stage_runs", "input_json")
    op.drop_column("stage_runs", "parent_stage_run_id")
    op.drop_column("stage_runs", "workflow_thread_id")
