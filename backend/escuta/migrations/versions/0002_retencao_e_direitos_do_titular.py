"""retencao e direitos do titular

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05 12:11:48.978782
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('anexo', schema=None) as batch_op:
        batch_op.add_column(sa.Column('descartado_em', sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table('consentimento', schema=None) as batch_op:
        batch_op.add_column(sa.Column('motivo_revogacao', sa.Text(), nullable=True))

    with op.batch_alter_table('manifestacao', schema=None) as batch_op:
        # server_default: obrigatório para linhas já existentes em produção
        batch_op.add_column(sa.Column('retencao_suspensa', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('descartado_em', sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table('pessoa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dados_removidos_em', sa.DateTime(timezone=True), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('pessoa', schema=None) as batch_op:
        batch_op.drop_column('dados_removidos_em')

    with op.batch_alter_table('manifestacao', schema=None) as batch_op:
        batch_op.drop_column('descartado_em')
        batch_op.drop_column('retencao_suspensa')

    with op.batch_alter_table('consentimento', schema=None) as batch_op:
        batch_op.drop_column('motivo_revogacao')

    with op.batch_alter_table('anexo', schema=None) as batch_op:
        batch_op.drop_column('descartado_em')

