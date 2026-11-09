"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-26 14:53:34.502239
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from geoalchemy2 import Geometry

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS postgis')
    op.create_geospatial_table('districts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('osm_id', sa.BigInteger(), nullable=False),
    sa.Column('name_en', sa.String(length=120), nullable=True),
    sa.Column('name_ar', sa.String(length=120), nullable=True),
    sa.Column('geom', Geometry(geometry_type='MULTIPOLYGON', srid=4326, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('osm_id')
    )
    op.create_geospatial_index('idx_districts_geom', 'districts', ['geom'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('role', sa.Enum('admin', 'manager', 'inspector', 'viewer', name='user_role'), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('processing_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Enum('sentinel2', 'osm_import', name='run_kind'), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'succeeded', 'failed', name='run_status'), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('requested_by', sa.Uuid(), nullable=True),
    sa.Column('scenes_found', sa.Integer(), nullable=False),
    sa.Column('scenes_processed', sa.Integer(), nullable=False),
    sa.Column('items_written', sa.Integer(), nullable=False),
    sa.Column('items_skipped', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('messages', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_processing_runs_status'), 'processing_runs', ['status'], unique=False)
    op.create_table('sessions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_geospatial_table('sites',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('name_ar', sa.String(length=120), nullable=True),
    sa.Column('site_type', sa.Enum('park', 'garden', 'median', 'plaza', 'other', name='site_type'), nullable=False),
    sa.Column('planting_category', sa.Enum('turf', 'shrubs', 'trees', 'native', 'mixed', 'unknown', name='planting_category'), nullable=False),
    sa.Column('district_id', sa.Integer(), nullable=True),
    sa.Column('geom', Geometry(geometry_type='MULTIPOLYGON', srid=4326, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('area_m2', sa.Float(), nullable=False),
    sa.Column('low_confidence', sa.Boolean(), nullable=False),
    sa.Column('needs_review', sa.Boolean(), nullable=False),
    sa.Column('status', sa.Enum('active', 'inactive', name='site_status'), nullable=False),
    sa.Column('source', sa.Enum('osm', 'manual', name='site_source'), nullable=False),
    sa.Column('source_ref', sa.String(length=64), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['district_id'], ['districts.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source', 'source_ref', name='uq_sites_source_ref')
    )
    op.create_geospatial_index('idx_sites_geom', 'sites', ['geom'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index(op.f('ix_sites_district_id'), 'sites', ['district_id'], unique=False)
    op.create_table('observations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('site_id', sa.Uuid(), nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=True),
    sa.Column('scene_id', sa.String(length=128), nullable=False),
    sa.Column('platform', sa.String(length=32), nullable=False),
    sa.Column('acquired_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('acquired_on', sa.Date(), nullable=False),
    sa.Column('processing_baseline', sa.String(length=8), nullable=False),
    sa.Column('ndvi_mean', sa.Float(), nullable=True),
    sa.Column('ndvi_std', sa.Float(), nullable=True),
    sa.Column('ndmi_mean', sa.Float(), nullable=True),
    sa.Column('ndmi_std', sa.Float(), nullable=True),
    sa.Column('valid_pixels', sa.Integer(), nullable=False),
    sa.Column('total_pixels', sa.Integer(), nullable=False),
    sa.Column('valid_share', sa.Float(), nullable=False),
    sa.Column('usable', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['processing_runs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('site_id', 'acquired_on', name='uq_observation_site_date')
    )
    op.create_index(op.f('ix_observations_site_id'), 'observations', ['site_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_observations_site_id'), table_name='observations')
    op.drop_table('observations')
    op.drop_index(op.f('ix_sites_district_id'), table_name='sites')
    op.drop_geospatial_index('idx_sites_geom', table_name='sites', postgresql_using='gist', column_name='geom')
    op.drop_geospatial_table('sites')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_index(op.f('ix_processing_runs_status'), table_name='processing_runs')
    op.drop_table('processing_runs')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_geospatial_index('idx_districts_geom', table_name='districts', postgresql_using='gist', column_name='geom')
    op.drop_geospatial_table('districts')
    for name in ('run_status', 'run_kind', 'site_source', 'site_status', 'planting_category', 'site_type', 'user_role'):
        op.execute(f'DROP TYPE IF EXISTS {name}')
