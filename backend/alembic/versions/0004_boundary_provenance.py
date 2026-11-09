"""Version spatial observations when a site's boundary changes; retain previous evidence.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sites", sa.Column("boundary_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("sites", sa.Column("boundary_history", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("weather_daily", sa.Column("boundary_version", sa.Integer(), nullable=False, server_default="1"))
    op.drop_constraint("uq_weather_site_day", "weather_daily", type_="unique")
    op.create_unique_constraint("uq_weather_site_day", "weather_daily", ["site_id", "day", "boundary_version"])
    for table, constraint in (("observations", "uq_observation_site_date"), ("lst_observations", "uq_lst_site_date")):
        op.add_column(table, sa.Column("boundary_version", sa.Integer(), nullable=False, server_default="1"))
        op.drop_constraint(constraint, table, type_="unique")
        op.create_unique_constraint(constraint, table, ["site_id", "acquired_on", "boundary_version"])


def downgrade():
    # A lossless downgrade is possible only before an acquisition has multiple boundary versions.
    op.drop_constraint("uq_weather_site_day", "weather_daily", type_="unique")
    op.create_unique_constraint("uq_weather_site_day", "weather_daily", ["site_id", "day"])
    op.drop_column("weather_daily", "boundary_version")
    for table, constraint in (("observations", "uq_observation_site_date"), ("lst_observations", "uq_lst_site_date")):
        op.drop_constraint(constraint, table, type_="unique")
        op.create_unique_constraint(constraint, table, ["site_id", "acquired_on"])
        op.drop_column(table, "boundary_version")
    op.drop_column("sites", "boundary_history")
    op.drop_column("sites", "boundary_version")
