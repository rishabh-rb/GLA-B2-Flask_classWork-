"""remove password column

Revision ID: 4a26f37a1f74
Revises: 
Create Date: 2026-02-09 10:57:25.228467

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4a26f37a1f74'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    # Fresh database path (e.g., first deploy on Render).
    if 'user' not in table_names:
        op.create_table(
            'user',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('username', sa.String(length=150), nullable=False),
            sa.Column('email', sa.String(length=150), nullable=False),
            sa.Column('password_hash', sa.String(length=200), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('username'),
            sa.UniqueConstraint('email'),
        )
        return

    # Existing database path from older schema.
    columns = {column['name'] for column in inspector.get_columns('user')}
    if 'password' in columns:
        with op.batch_alter_table('user', schema=None) as batch_op:
            batch_op.drop_column('password')


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if 'user' not in table_names:
        return

    columns = {column['name'] for column in inspector.get_columns('user')}
    if 'password' not in columns:
        with op.batch_alter_table('user', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('password', sa.VARCHAR(length=200), autoincrement=False, nullable=False)
            )
