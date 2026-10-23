"""real data: phone SMS sync state, IMAP mailboxes, wishlist price tracking; the demo-store catalogue is removed

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.core.money

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Goals point at wishlist items now, not at products from the (removed) demo stores.
    with op.batch_alter_table('goals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('wishlist_item_id', sa.Integer(), nullable=True))
        batch_op.drop_constraint('fk_goals_product_id_products', type_='foreignkey')
        batch_op.drop_column('product_id')
        batch_op.create_foreign_key(batch_op.f('fk_goals_wishlist_item_id_wishlist_items'), 'wishlist_items',
                                    ['wishlist_item_id'], ['id'], ondelete='SET NULL')

    for table, indexes in (
        ('product_recommendations', ('ix_product_recommendations_user_id', 'ix_product_recommendations_batch')),
        ('product_price_history', ('ix_product_price_history_product_id',)),
        ('products', ('ix_products_source_id', 'ix_products_sku', 'ix_products_category')),
        ('affordability_snapshots', ('ix_affordability_snapshots_user_id',)),
    ):
        with op.batch_alter_table(table, schema=None) as batch_op:
            for ix in indexes:
                batch_op.drop_index(ix)
        op.drop_table(table)
    op.drop_table('product_sources')
    op.drop_table('crawl_runs')

    with op.batch_alter_table('wishlist_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('price', app.core.money.Money(), nullable=True))
        batch_op.add_column(sa.Column('price_source', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('url', sa.String(length=1000), nullable=True))
        batch_op.add_column(sa.Column('store', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('image_url', sa.String(length=1000), nullable=True))
        batch_op.add_column(sa.Column('fetch_status', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('fetch_note', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('last_checked_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('bought_at', sa.DateTime(), nullable=True))

    op.create_table('wishlist_price_points',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('price', app.core.money.Money(), nullable=False),
    sa.Column('observed_on', sa.Date(), nullable=False),
    sa.Column('source', sa.String(length=8), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['wishlist_items.id'], name=op.f('fk_wishlist_price_points_item_id_wishlist_items'),
                            ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wishlist_price_points'))
    )
    with op.batch_alter_table('wishlist_price_points', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wishlist_price_points_item_id'), ['item_id'], unique=False)

    with op.batch_alter_table('data_sources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sync_state', sa.JSON(), nullable=True))

    op.create_table('mailbox_connections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('data_source_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('host', sa.String(length=120), nullable=False),
    sa.Column('port', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=255), nullable=False),
    sa.Column('secret_enc', sa.LargeBinary(), nullable=True),
    sa.Column('folder', sa.String(length=255), nullable=True),
    sa.Column('uidvalidity', sa.Integer(), nullable=True),
    sa.Column('last_uid', sa.Integer(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(), nullable=True),
    sa.Column('last_error', sa.String(length=255), nullable=True),
    sa.Column('last_counts', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_sources.id'], name=op.f('fk_mailbox_connections_data_source_id_data_sources'),
                            ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_mailbox_connections_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_mailbox_connections')),
    sa.UniqueConstraint('user_id', name=op.f('uq_mailbox_connections_user_id'))
    )
    with op.batch_alter_table('mailbox_connections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mailbox_connections_data_source_id'), ['data_source_id'], unique=False)

    with op.batch_alter_table('balance_snapshots', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=10), nullable=False, server_default='alert'))

    # Merchants a user names themselves are private to them; the curated list stays global (user_id NULL).
    with op.batch_alter_table('merchants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.drop_constraint('uq_merchants_name', type_='unique')
        batch_op.create_foreign_key(batch_op.f('fk_merchants_user_id_users'), 'users', ['user_id'], ['id'], ondelete='CASCADE')
        batch_op.create_unique_constraint(batch_op.f('uq_merchants_user_id_name'), ['user_id', 'name'])
        batch_op.create_index(batch_op.f('ix_merchants_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    raise NotImplementedError("FinPilot AI 2.0 removed the demo-store catalogue; restore a backup to go back to 1.x.")
