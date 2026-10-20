#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


def positive_id(value):
    if not re.fullmatch(r'[1-9][0-9]{0,18}', value):
        raise ValueError(f'Identificador inválido: {value!r}')
    return value


def build_manifest(rows, batch):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', batch):
        raise ValueError('Lote inválido.')
    companies = {}
    order_ids = set()
    for row in rows:
        tenant_id = positive_id(row['tenant_id'])
        order_id = positive_id(row['pedido_id'])
        counts = (int(row['total_clientes']), int(row['total_pedidos']), int(row['total_itens']))
        if counts != (5000, 20000, 60000):
            raise ValueError(f'Empresa {tenant_id}: esperado 5000 clientes, 20000 pedidos e 60000 itens.')
        if not row['empresa_nome'].startswith(f'TCC-{batch} Empresa '):
            raise ValueError(f'Empresa fora do lote {batch}.')
        if row['pedido_status'] != 'ABERTO':
            raise ValueError('Os pedidos reservados precisam iniciar ABERTO.')
        company = companies.setdefault(tenant_id, {
            'tenant_id': tenant_id,
            'name': row['empresa_nome'],
            'total_clients': 5000,
            'total_orders': 20000,
            'total_items': 60000,
            'write_orders': [],
        })
        if company['name'] != row['empresa_nome'] or int(row['slot']) != len(company['write_orders']):
            raise ValueError('Linhas precisam estar ordenadas por empresa e slot, sem duplicação.')
        if order_id in order_ids:
            raise ValueError(f'Pedido repetido: {order_id}.')
        order_ids.add(order_id)
        company['write_orders'].append({'id': order_id, 'initial_status': 'ABERTO'})
    ordered = sorted(companies.values(), key=lambda company: int(company['tenant_id']))
    if len(ordered) != 100 or any(len(company['write_orders']) != 20 for company in ordered):
        raise ValueError('O manifesto exige 100 empresas e 20 pedidos reservados por empresa.')
    return {
        'schema_version': 1,
        'batch': batch,
        'company_count': 100,
        'active_company_count': 25,
        'page_size': 20,
        'sort': ['criadoEm,desc', 'id,desc'],
        'companies': ordered,
    }


def main():
    parser = argparse.ArgumentParser(description='Valida CSV com IDs reais; não conecta nem altera bancos.')
    parser.add_argument('--csv', type=Path, required=True)
    parser.add_argument('--lote', required=True)
    parser.add_argument('--saida', type=Path, required=True)
    arguments = parser.parse_args()
    try:
        with arguments.csv.open(newline='', encoding='utf-8') as source:
            manifest = build_manifest(csv.DictReader(source), arguments.lote)
        content = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
        with arguments.saida.open('x', encoding='utf-8') as output:
            output.write(content)
    except (ValueError, KeyError) as error:
        parser.error(str(error))
    print(f'Manifesto: {arguments.saida}; SHA-256: {hashlib.sha256(content.encode()).hexdigest()}')


if __name__ == '__main__':
    main()
