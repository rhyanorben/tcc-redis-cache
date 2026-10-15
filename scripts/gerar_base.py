#!/usr/bin/env python3
"""Gera SQL reproduzível; não conecta a bancos nem executa alterações."""
import argparse
import re
from pathlib import Path


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Informe um inteiro positivo.')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--empresas', type=positive, required=True)
    parser.add_argument('--pedidos-por-empresa', type=positive, required=True)
    parser.add_argument('--clientes-por-empresa', type=positive, default=10)
    parser.add_argument('--lote', default='exp-001', help='Identificador único da carga; não reutilize.')
    parser.add_argument('--saida', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', args.lote):
        parser.error('--lote deve ter 1 a 40 letras, números, hífens ou sublinhados.')
    prefix = 'TCC-' + args.lote
    sql = f"""-- Gerado por scripts/gerar_base.py. Revise e autorize antes de aplicar.
-- {args.empresas} empresas, {args.clientes_por_empresa} clientes e {args.pedidos_por_empresa} pedidos por empresa.
\\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path = tcc, pg_catalog;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM empresa WHERE starts_with(nome, '{prefix} Empresa ')) THEN
        RAISE EXCEPTION 'Lote já existe. Nenhum dado será removido ou substituído.';
    END IF;
END $$;
CREATE TEMP TABLE seed_empresas(id bigint) ON COMMIT DROP;
CREATE TEMP TABLE seed_pedidos(id bigint, tenant_id bigint) ON COMMIT DROP;
WITH novas AS (
    INSERT INTO empresa(nome)
    SELECT '{prefix} Empresa ' || n FROM generate_series(1, {args.empresas}) n
    RETURNING id
)
INSERT INTO seed_empresas SELECT id FROM novas;
INSERT INTO cliente(tenant_id, nome)
SELECT e.id, 'Cliente ' || n FROM seed_empresas e
CROSS JOIN generate_series(1, {args.clientes_por_empresa}) n;
WITH novos AS (
    INSERT INTO pedido(tenant_id, cliente_id, total, criado_em, atualizado_em)
    SELECT e.id, c.id, 10.00,
           timestamptz '2026-01-01 00:00:00+00' + n * interval '1 second',
           timestamptz '2026-01-01 00:00:00+00' + n * interval '1 second'
    FROM seed_empresas e CROSS JOIN generate_series(1, {args.pedidos_por_empresa}) n
    JOIN cliente c ON c.tenant_id = e.id
       AND c.nome = 'Cliente ' || (((n - 1) % {args.clientes_por_empresa}) + 1)
    RETURNING id, tenant_id
)
INSERT INTO seed_pedidos SELECT id, tenant_id FROM novos;
INSERT INTO item_pedido(tenant_id, pedido_id, descricao, quantidade, preco_unitario)
SELECT tenant_id, id, 'Item experimental', 1, 10.00 FROM seed_pedidos;
COMMIT;
-- Execute como proprietário das tabelas para atualizar estatísticas antes dos ensaios.
ANALYZE tcc.empresa;
ANALYZE tcc.cliente;
ANALYZE tcc.pedido;
ANALYZE tcc.item_pedido;
SELECT id, nome FROM tcc.empresa WHERE starts_with(nome, '{prefix} Empresa ') ORDER BY id;
"""
    # Falha se o arquivo existir; não sobrescreve uma carga já revisada.
    with args.saida.open('x', encoding='utf-8') as output:
        output.write(sql)
    print(f'SQL gerado em {args.saida}; nenhuma conexão ou alteração no banco foi realizada.')


if __name__ == '__main__':
    main()
