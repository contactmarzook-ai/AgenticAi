"""organizations (tenants), new roles, sign-in sessions, OIDC users

Existing data moves into one "Default organization" (id 1). Roles are renamed:
admin -> platform_admin, builder -> developer, user -> operator.

Revision ID: a1c3e5f7b9d2
Revises: f8f52cef6e2e
Create Date: 2026-11-21 12:00:00
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, None] = "f8f52cef6e2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = ["users", "agents", "workflows", "runs", "triggers", "credentials"]
ROLE_RENAMES = {"admin": "platform_admin", "builder": "developer", "user": "operator"}
CONN_ROLE_RENAMES = {"builder": "developer", "admin": "org_admin"}


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True)
    orgs = sa.table(
        "organizations",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        orgs.insert().values(id=1, name="Default organization", slug="default", is_active=True, created_at=sa.func.now())
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SELECT setval(pg_get_serial_sequence('organizations', 'id'), 1)")

    for table in TENANT_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("org_id", sa.Integer(), nullable=False, server_default="1"))
            batch.create_index(f"ix_{table}_org_id", ["org_id"], unique=False)
            batch.create_foreign_key(f"fk_{table}_org_id", "organizations", ["org_id"], ["id"], ondelete="RESTRICT")
        with op.batch_alter_table(table) as batch:
            batch.alter_column("org_id", server_default=None)

    with op.batch_alter_table("audit_logs") as batch:
        batch.add_column(sa.Column("org_id", sa.Integer(), nullable=True))
        batch.create_index("ix_audit_logs_org_id", ["org_id"], unique=False)
        batch.create_foreign_key("fk_audit_logs_org_id", "organizations", ["org_id"], ["id"], ondelete="SET NULL")
    op.execute("UPDATE audit_logs SET org_id = 1")

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("auth_provider", sa.String(length=20), nullable=False, server_default="local"))
        batch.add_column(sa.Column("oidc_subject", sa.String(length=255), nullable=True))
        batch.create_unique_constraint("uq_users_oidc_subject", ["oidc_subject"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("refresh_hash", sa.String(length=64), nullable=False),
        sa.Column("prev_refresh_hash", sa.String(length=64), nullable=True),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_hash"),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)
    op.create_index(op.f("ix_auth_sessions_prev_refresh_hash"), "auth_sessions", ["prev_refresh_hash"], unique=False)

    _rename_roles(ROLE_RENAMES, CONN_ROLE_RENAMES)


def _rename_roles(roles: dict, conn_roles: dict) -> None:
    bind = op.get_bind()
    for old, new in roles.items():
        bind.execute(sa.text("UPDATE users SET role = :new WHERE role = :old"), {"new": new, "old": old})
    for mid, raw in bind.execute(sa.text("SELECT id, allowed_roles FROM llm_models")).fetchall():
        current = json.loads(raw) if isinstance(raw, str) else (raw or [])
        renamed = [roles.get(r, r) for r in current]
        if renamed != current:
            bind.execute(
                sa.text("UPDATE llm_models SET allowed_roles = :v WHERE id = :id"), {"v": json.dumps(renamed), "id": mid}
            )
    row = bind.execute(sa.text("SELECT value FROM platform_settings WHERE key = 'platform'")).fetchone()
    if row is not None:
        value = json.loads(row[0]) if isinstance(row[0], str) else dict(row[0] or {})
        if value.get("connections_min_role") in conn_roles:
            value["connections_min_role"] = conn_roles[value["connections_min_role"]]
            bind.execute(
                sa.text("UPDATE platform_settings SET value = :v WHERE key = 'platform'"), {"v": json.dumps(value)}
            )


def downgrade() -> None:
    _rename_roles(
        {"platform_admin": "admin", "org_admin": "admin", "developer": "builder", "operator": "user",
         "viewer": "user", "auditor": "user"},
        {"developer": "builder", "org_admin": "admin"},
    )
    op.drop_index(op.f("ix_auth_sessions_prev_refresh_hash"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_oidc_subject", type_="unique")
        batch.drop_column("oidc_subject")
        batch.drop_column("auth_provider")
    for table in ["audit_logs", *TENANT_TABLES]:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_org_id", type_="foreignkey")
            batch.drop_index(f"ix_{table}_org_id")
            batch.drop_column("org_id")
    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations")
    op.drop_table("organizations")
