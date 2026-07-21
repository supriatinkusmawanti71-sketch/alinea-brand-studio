"""Add immutable user decisions for workflow resumes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_decisions"
down_revision: str | None = "0003_workflow_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column(
            "source_version_id",
            sa.String(length=36),
            sa.ForeignKey("stage_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("selected_item_id", sa.String(length=120), nullable=True),
        sa.Column(
            "resulting_stage_run_id",
            sa.String(length=36),
            sa.ForeignKey("stage_runs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_version_id",
            "action",
            name="uq_decision_source_version_action",
        ),
    )
    op.create_index(
        "ix_decisions_project_stage",
        "decisions",
        ["project_id", "stage"],
    )


def downgrade() -> None:
    op.drop_index("ix_decisions_project_stage", table_name="decisions")
    op.drop_table("decisions")
