"""agent contracts (input/output JSON Schema), capabilities and tags

Existing agents get the default contract {message: string} -> {answer: string}, which is what
they already accepted and returned.

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-11-21 14:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4f6a8c0e1"
down_revision: Union[str, None] = "a1c3e5f7b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_INPUT = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": False,
}
DEFAULT_OUTPUT = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def upgrade() -> None:
    with op.batch_alter_table("agents") as batch:
        for name in ("input_schema", "output_schema", "capabilities", "tags"):
            batch.add_column(sa.Column(name, sa.JSON(), nullable=True))
    agents = sa.table(
        "agents",
        sa.column("input_schema", sa.JSON),
        sa.column("output_schema", sa.JSON),
        sa.column("capabilities", sa.JSON),
        sa.column("tags", sa.JSON),
    )
    op.execute(agents.update().values(input_schema=DEFAULT_INPUT, output_schema=DEFAULT_OUTPUT, capabilities=[], tags=[]))
    with op.batch_alter_table("agents") as batch:
        for name in ("input_schema", "output_schema", "capabilities", "tags"):
            batch.alter_column(name, existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("agents") as batch:
        for name in ("tags", "capabilities", "output_schema", "input_schema"):
            batch.drop_column(name)


