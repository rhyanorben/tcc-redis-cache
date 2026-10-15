#!/usr/bin/env python3
import argparse
import re
from pathlib import Path


def positive_integer(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Informe um inteiro positivo.')
    return number


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Gera SQL reproduzível; não conecta a bancos nem executa alterações.'
    )
    parser.add_argument('--empresas', type=positive_integer, required=True)
    parser.add_argument('--pedidos-por-empresa', type=positive_integer, required=True)
    parser.add_argument('--clientes-por-empresa', type=positive_integer, default=10)
    parser.add_argument('--lote', default='exp-001', help='Identificador único da carga; não reutilize.')
    parser.add_argument('--saida', type=Path, required=True)
    arguments = parser.parse_args()

    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', arguments.lote):
        parser.error('--lote deve ter 1 a 40 letras, números, hífens ou sublinhados.')

    return arguments


def batch_guard_sql(batch_prefix):
    return f"""DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM empresa WHERE starts_with(nome, '{batch_prefix} Empresa ')) THEN
        RAISE EXCEPTION 'Lote já existe. Nenhum dado será removido ou substituído.';
    END IF;
END $$;"""


def companies_sql(batch_prefix, company_count):
    return f"""WITH novas AS (
    INSERT INTO empresa(nome)
    SELECT '{batch_prefix} Empresa ' || n FROM generate_series(1, {company_count}) n
    RETURNING id
)
INSERT INTO seed_empresas SELECT id FROM novas;"""


def customers_sql(customers_per_company):
    return f"""INSERT INTO cliente(tenant_id, nome)
SELECT e.id, 'Cliente ' || n FROM seed_empresas e
CROSS JOIN generate_series(1, {customers_per_company}) n;"""


def orders_sql(orders_per_company, customers_per_company):
    return f"""WITH novos AS (
    INSERT INTO pedido(tenant_id, cliente_id, total, criado_em, atualizado_em)
    SELECT e.id, c.id, 10.00,
           timestamptz '2026-01-01 00:00:00+00' + n * interval '1 second',
           timestamptz '2026-01-01 00:00:00+00' + n * interval '1 second'
    FROM seed_empresas e CROSS JOIN generate_series(1, {orders_per_company}) n
    JOIN cliente c ON c.tenant_id = e.id
       AND c.nome = 'Cliente ' || (((n - 1) % {customers_per_company}) + 1)
    RETURNING id, tenant_id
)
INSERT INTO seed_pedidos SELECT id, tenant_id FROM novos;"""


def order_items_sql():
    return """INSERT INTO item_pedido(tenant_id, pedido_id, descricao, quantidade, preco_unitario)
SELECT tenant_id, id, 'Item experimental', 1, 10.00 FROM seed_pedidos;"""


def build_seed_sql(arguments):
    batch_prefix = f'TCC-{arguments.lote}'
    statements = [
        r'\set ON_ERROR_STOP on',
        'BEGIN;',
        'SET LOCAL search_path = tcc, pg_catalog;',
        batch_guard_sql(batch_prefix),
        'CREATE TEMP TABLE seed_empresas(id bigint) ON COMMIT DROP;',
        'CREATE TEMP TABLE seed_pedidos(id bigint, tenant_id bigint) ON COMMIT DROP;',
        companies_sql(batch_prefix, arguments.empresas),
        customers_sql(arguments.clientes_por_empresa),
        orders_sql(arguments.pedidos_por_empresa, arguments.clientes_por_empresa),
        order_items_sql(),
        'COMMIT;',
        'ANALYZE tcc.empresa;',
        'ANALYZE tcc.cliente;',
        'ANALYZE tcc.pedido;',
        'ANALYZE tcc.item_pedido;',
        f"SELECT id, nome FROM tcc.empresa WHERE starts_with(nome, '{batch_prefix} Empresa ') ORDER BY id;",
    ]
    return '\n'.join(statements) + '\n'


def main():
    arguments = parse_arguments()
    seed_sql = build_seed_sql(arguments)

    with arguments.saida.open('x', encoding='utf-8') as output:
        output.write(seed_sql)

    print(f'SQL gerado em {arguments.saida}; nenhuma conexão ou alteração no banco foi realizada.')


if __name__ == '__main__':
    main()
