"""durable workflow runs: per-step records, worker lease, cancellation, publish metadata

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-11-21 16:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3e5a7b9d1f2"
down_revision: Union[str, None] = "b2d4f6a8c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("worker_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("resume_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("workflows") as batch:
        batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("published_by", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_workflows_published_by", "users", ["published_by"], ["id"], ondelete="SET NULL")
    # Versions that are or were live count as published (best available timestamp).
    op.execute(
        "UPDATE workflows SET published_at = updated_at, published_by = owner_id "
        "WHERE status = 'active' OR (status = 'archived' AND id IN (SELECT DISTINCT target_id FROM runs "
        "WHERE target_type = 'workflow' AND source <> 'test'))"
    )
    op.create_table(
        "run_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("continued", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("logs", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "node_id", name="uq_run_node"),
    )
    op.create_index(op.f("ix_run_nodes_run_id"), "run_nodes", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_run_nodes_run_id"), table_name="run_nodes")
    op.drop_table("run_nodes")
    with op.batch_alter_table("workflows") as batch:
        batch.drop_constraint("fk_workflows_published_by", type_="foreignkey")
        batch.drop_column("published_by")
        batch.drop_column("published_at")
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("cancel_requested")
        batch.drop_column("resume_count")
        batch.drop_column("heartbeat_at")
        batch.drop_column("worker_id")
