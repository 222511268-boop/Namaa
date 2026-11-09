"""sprint 3: water, heat, activity record, AI briefs

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Plant factors from the landscape coefficient method (WUCOLS IV, University of California). This guidance comes
# from outside Saudi Arabia, so the values are starting assumptions that managers can adjust.
PLANT_FACTORS = [
    ("turf", 0.6, "Warm-season turf: WUCOLS IV 0.6 (range 0.6-0.8). Guidance from outside KSA; adjustable assumption."),
    ("shrubs", 0.5, "Moderate water-use shrubs: WUCOLS IV 0.4-0.6. Guidance from outside KSA; adjustable assumption."),
    ("trees", 0.5, "Moderate water-use trees: WUCOLS IV 0.4-0.6. Guidance from outside KSA; adjustable assumption."),
    (
        "native",
        0.2,
        "Low water-use, desert-adapted plants: WUCOLS IV 0.1-0.3. Guidance from outside KSA; adjustable assumption.",
    ),
    (
        "mixed",
        0.5,
        "Mixed planting, moderate water use: WUCOLS IV 0.4-0.6. Guidance from outside KSA; adjustable assumption.",
    ),
    ("unknown", 0.5, "Planting not recorded; moderate water use assumed. Adjustable assumption."),
]


def upgrade() -> None:
    # New run types. ADD VALUE must be committed before the values can be used.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE run_kind ADD VALUE IF NOT EXISTS 'landsat_lst'")
        op.execute("ALTER TYPE run_kind ADD VALUE IF NOT EXISTS 'weather'")

    op.add_column("sites", sa.Column("irrigated_area_m2", sa.Float(), nullable=True))

    category = postgresql.ENUM(name="planting_category", create_type=False)
    op.create_table(
        "plant_factors",
        sa.Column("category", category, nullable=False),
        sa.Column("factor", sa.Float(), nullable=False),
        sa.Column("source_note", sa.String(length=300), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("category"),
    )
    for cat, factor, note in PLANT_FACTORS:
        op.execute(
            sa.text(
                "INSERT INTO plant_factors (category, factor, source_note) "
                "VALUES (CAST(:c AS planting_category), :f, :n)"
            ).bindparams(c=cat, f=factor, n=note)
        )

    op.create_table(
        "weather_daily",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("et0_mm", sa.Float(), nullable=True),
        sa.Column("tmax_c", sa.Float(), nullable=True),
        sa.Column("tmin_c", sa.Float(), nullable=True),
        sa.Column("precip_mm", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "day", name="uq_weather_site_day"),
    )
    op.create_index(op.f("ix_weather_daily_site_id"), "weather_daily", ["site_id"])

    op.create_table(
        "irrigation_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("weekdays", sa.JSON(), nullable=False),
        sa.Column("litres_per_day", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_irrigation_schedules_site_id"), "irrigation_schedules", ["site_id"])

    op.create_table(
        "lst_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("scene_id", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("acquired_on", sa.Date(), nullable=False),
        sa.Column("site_c", sa.Float(), nullable=True),
        sa.Column("surround_c", sa.Float(), nullable=True),
        sa.Column("site_pixels", sa.Integer(), nullable=False),
        sa.Column("surround_pixels", sa.Integer(), nullable=False),
        sa.Column("valid_share", sa.Float(), nullable=False),
        sa.Column("usable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["processing_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "acquired_on", name="uq_lst_site_date"),
    )
    op.create_index(op.f("ix_lst_observations_site_id"), "lst_observations", ["site_id"])

    op.create_table(
        "lst_layers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("acquired_on", sa.Date(), nullable=False),
        sa.Column("image", sa.String(length=80), nullable=False),
        sa.Column("bounds", sa.JSON(), nullable=False),
        sa.Column("min_c", sa.Float(), nullable=False),
        sa.Column("max_c", sa.Float(), nullable=False),
        sa.Column("valid_share", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scene_id"),
    )
    op.create_index(op.f("ix_lst_layers_acquired_on"), "lst_layers", ["acquired_on"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("user_name", sa.String(length=120), nullable=True),
        sa.Column("user_role", sa.String(length=16), nullable=True),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_at"), "audit_events", ["at"])
    op.create_index(op.f("ix_audit_events_user_id"), "audit_events", ["user_id"])
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"])
    # The activity record is append-only: reject row updates and deletes at the database level.
    op.execute(
        """
        CREATE FUNCTION audit_events_read_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_change BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit_events_read_only()"
    )

    op.create_table(
        "ai_briefs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("subject_key", sa.String(length=200), nullable=False),
        sa.Column("facts_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_briefs_subject", "ai_briefs", ["kind", "subject_key"])


def downgrade() -> None:
    op.drop_index("ix_ai_briefs_subject", table_name="ai_briefs")
    op.drop_table("ai_briefs")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_change ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_read_only()")
    op.drop_table("audit_events")
    op.drop_table("lst_layers")
    op.drop_table("lst_observations")
    op.drop_table("irrigation_schedules")
    op.drop_table("weather_daily")
    op.drop_table("plant_factors")
    op.drop_column("sites", "irrigated_area_m2")
    # PostgreSQL cannot drop enum values; the added run_kind values remain unused after a downgrade.
