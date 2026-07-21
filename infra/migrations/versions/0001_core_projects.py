"""Create projects, workflow results, model audit, and outbox tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_core_projects"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=100), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=True),
        sa.Column("current_stage", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *timestamp_columns(),
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])

    op.create_table(
        "brand_specs",
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("source_map_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *timestamp_columns(),
    )

    op.create_table(
        "stage_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("result_version_id", sa.String(length=36), nullable=True),
        *timestamp_columns(),
        sa.UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_stage_run_idempotency",
        ),
    )
    op.create_index(
        "ix_stage_runs_project_stage_status",
        "stage_runs",
        ["project_id", "stage", "status"],
    )

    op.create_table(
        "stage_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stage_run_id",
            sa.String(length=36),
            sa.ForeignKey("stage_runs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("input_refs_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_id",
            "stage",
            "version_no",
            name="uq_stage_version_number",
        ),
    )
    op.create_foreign_key(
        "fk_stage_runs_result_version",
        "stage_runs",
        "stage_versions",
        ["result_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "model_invocations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "stage_run_id",
            sa.String(length=36),
            sa.ForeignKey("stage_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(length=200), nullable=False),
        sa.Column("capability", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_model_invocations_stage_run_id",
        "model_invocations",
        ["stage_run_id"],
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        *timestamp_columns(),
    )
    op.create_index(
        "ix_outbox_status_created",
        "outbox_events",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_status_created", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_model_invocations_stage_run_id", table_name="model_invocations")
    op.drop_table("model_invocations")
    op.drop_constraint("fk_stage_runs_result_version", "stage_runs", type_="foreignkey")
    op.drop_table("stage_versions")
    op.drop_index("ix_stage_runs_project_stage_status", table_name="stage_runs")
    op.drop_table("stage_runs")
    op.drop_table("brand_specs")
    op.drop_index("ix_projects_workspace_id", table_name="projects")
    op.drop_table("projects")
