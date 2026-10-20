#!/usr/bin/env python3
import argparse
import json
import math
import re
import statistics
from datetime import datetime
from pathlib import Path


REDIS_COUNTERS = ('keyspace_hits', 'keyspace_misses', 'evicted_keys', 'expired_keys',
                  'total_error_replies', 'total_commands_processed')
SQL_COUNTERS = ('calls', 'rows', 'total_exec_time', 'shared_blks_hit', 'shared_blks_read',
                'shared_blks_dirtied', 'shared_blks_written')


def counter_delta(before, after, keys):
    result = {}
    for key in keys:
        if key not in before or key not in after:
            raise ValueError(f'Contador ausente: {key}')
        value = after[key] - before[key]
        if value < 0:
            raise ValueError(f'Contador diminuiu durante a coleta: {key}')
        result[key] = value
    return result


def memory_bytes(value):
    match = re.fullmatch(r'([0-9.]+)\s*([KMGTPE]?i?B)', value.strip())
    if not match:
        raise ValueError('Unidade de memória Docker desconhecida')
    unit = match.group(2)
    exponent = 'BKMGTPE'.index(unit[0]) if unit != 'B' else 0
    return float(match.group(1)) * (1024 if 'i' in unit else 1000) ** exponent


def distribution(values):
    return {'mean': statistics.mean(values), 'minimum': min(values), 'maximum': max(values)}


def resource_summary(samples):
    if len({sample['docker']['ID'] for sample in samples}) != 1:
        raise ValueError('O contêiner foi substituído durante a coleta')
    cpu = [float(sample['docker']['CPUPerc'].rstrip('%')) for sample in samples]
    memory = [memory_bytes(sample['docker']['MemUsage'].split('/')[0]) for sample in samples]
    return {'docker_cpu_percent': distribution(cpu), 'docker_memory_bytes': distribution(memory)}


def summarize_application(before, after):
    if before.get('process_start_time') is None or after.get('process_start_time') is None:
        raise ValueError('Identificação de início da aplicação ausente')
    if before['process_start_time'] != after['process_start_time']:
        raise ValueError('A aplicação reiniciou durante a coleta')
    if before['cache_instrumented'] != after['cache_instrumented']:
        raise ValueError('A instrumentação do cache mudou durante a coleta')
    result = counter_delta(before, after, [key for key in before if key.startswith('tcc.cache.')])
    accesses = sum(result['tcc.cache.requests.' + outcome] for outcome in ('hit', 'miss', 'fallback'))
    result['logical_hit_ratio'] = result['tcc.cache.requests.hit'] / accesses if accesses else None
    result['cache_instrumented'] = after['cache_instrumented']
    return result


def summarize_postgres(before, after):
    if before.get('postmaster_start_time') is None or after.get('postmaster_start_time') is None:
        raise ValueError('Identificação de início do PostgreSQL ausente')
    if before['postmaster_start_time'] != after['postmaster_start_time']:
        raise ValueError('O PostgreSQL reiniciou durante a coleta')
    if before['stats_reset'] != after['stats_reset'] or before['dealloc'] != after['dealloc']:
        raise ValueError('Estatísticas PostgreSQL reiniciadas ou descartadas')
    previous = {item['queryid']: item for item in before['statements']}
    current = {item['queryid']: item for item in after['statements']}
    if not previous.keys() <= current.keys():
        raise ValueError('Uma consulta desapareceu das estatísticas PostgreSQL')
    statements = []
    for query_id, statement in current.items():
        initial = previous.get(query_id, dict.fromkeys(SQL_COUNTERS, 0))
        changes = counter_delta(initial, statement, SQL_COUNTERS)
        statements.append({'queryid': query_id, 'query': statement['query'], **changes})
    return {'statements': statements,
            'totals': {key: sum(item[key] for item in statements) for key in SQL_COUNTERS}}


def summarize_redis(before, after, samples):
    if not before.get('run_id') or not after.get('run_id'):
        raise ValueError('Identificação de início do Redis ausente')
    if before['run_id'] != after['run_id']:
        raise ValueError('O Redis reiniciou durante a coleta')
    if before['maxmemory'] != after['maxmemory'] or before['maxmemory_policy'] != after['maxmemory_policy']:
        raise ValueError('A configuração de memória do Redis mudou durante a coleta')
    result = {'counters': counter_delta(before, after, REDIS_COUNTERS)}
    for key in ('used_memory', 'used_memory_dataset', 'used_memory_rss'):
        result[key] = distribution([sample['redis'][key] for sample in samples])
    result['maxmemory'] = after['maxmemory']
    result['maxmemory_policy'] = after['maxmemory_policy']
    return result


def timestamp_ms(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp deve informar fuso horário')
    return parsed.timestamp() * 1000


def select_window(samples, window, max_boundary_gap_seconds):
    start = window['measurement_start_unix_ms']
    end = window['measurement_end_unix_ms']
    completed = window['measurement_completed_unix_ms']
    if window.get('valid') is False or window.get('valid_for_campaign') is False:
        raise ValueError('O resultado k6 foi marcado como inválido para a campanha')
    if window.get('phase', 'measurement') not in ('measurement', 'full'):
        raise ValueError('O resumo k6 não corresponde à medição')
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in (start, end, completed)):
        raise ValueError('Horários k6 devem ser números finitos')
    if not start < end <= completed:
        raise ValueError('Janela de medição k6 inválida')
    if abs(end - start - 300000) > 1:
        raise ValueError('A medição da campanha deve durar 300 segundos')
    before = [sample for sample in samples if timestamp_ms(sample['completed_at']) <= start]
    after = [sample for sample in samples if timestamp_ms(sample['timestamp']) >= completed]
    resources = [sample for sample in samples if timestamp_ms(sample['timestamp']) >= start
                 and timestamp_ms(sample['completed_at']) <= end]
    if not before or not after or len(resources) < 2:
        raise ValueError('A coleta não cobre a medição e suas margens')
    initial, final = before[-1], after[0]
    before_gap = (start - timestamp_ms(initial['completed_at'])) / 1000
    after_gap = (timestamp_ms(final['timestamp']) - completed) / 1000
    if max(before_gap, after_gap) > max_boundary_gap_seconds:
        raise ValueError('Margem de coleta excedida; confira relógios e início dos coletores')
    return initial, final, resources


def summarize(samples, window=None, max_boundary_gap_seconds=15):
    if len(samples) < 2:
        raise ValueError('São necessárias ao menos duas amostras')
    if any('error' in sample for sample in samples):
        raise ValueError('Há falhas de coleta; a execução precisa ser revisada')
    if len({sample['service'] for sample in samples}) != 1:
        raise ValueError('Mistura de serviços no mesmo arquivo')
    service = samples[0]['service']
    for sample in samples:
        if not math.isfinite(sample['elapsed_seconds']) or sample['elapsed_seconds'] < 0:
            raise ValueError('Tempo decorrido inválido')
        if timestamp_ms(sample['completed_at']) < timestamp_ms(sample['timestamp']):
            raise ValueError('Uma amostra terminou antes de começar')
    resource_summary(samples)
    for before, after in zip(samples, samples[1:]):
        if after['elapsed_seconds'] <= before['elapsed_seconds']:
            raise ValueError('A ordem das amostras não é crescente')
        if timestamp_ms(after['timestamp']) < timestamp_ms(before['completed_at']):
            raise ValueError('O relógio regrediu ou amostras se sobrepõem')
        if service == 'app':
            summarize_application(before['application'], after['application'])
        elif service == 'postgres':
            summarize_postgres(before['postgres'], after['postgres'])
        elif service == 'redis':
            summarize_redis(before['redis'], after['redis'], [before, after])
        else:
            raise ValueError('Serviço desconhecido')
    initial, final, resources = samples[0], samples[-1], samples
    if window is not None:
        initial, final, resources = select_window(samples, window, max_boundary_gap_seconds)
    result = {'service': service, 'started_at': initial['timestamp'], 'ended_at': final['completed_at'],
              'sample_count': len(samples), 'resource_sample_count': len(resources),
              'scope': 'collection' if window is None else 'measurement_resources_with_bracketed_counters',
              **resource_summary(resources)}
    if window is not None:
        result['measurement_window'] = {key: window[key] for key in (
            'measurement_start_unix_ms', 'measurement_end_unix_ms', 'measurement_completed_unix_ms')}
        result['counter_window'] = {'started_at': initial['timestamp'], 'ended_at': final['completed_at'],
                                    'requires_quiet_margins': True}
    if service == 'app':
        result['application'] = summarize_application(initial['application'], final['application'])
    elif service == 'postgres':
        result['postgres'] = summarize_postgres(initial['postgres'], final['postgres'])
    else:
        result['redis'] = summarize_redis(initial['redis'], final['redis'], resources)
    return result


def main():
    parser = argparse.ArgumentParser(description='Resume amostras por execução usando diferenças de contadores.')
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--measurement-summary', type=Path)
    parser.add_argument('--max-boundary-gap-seconds', type=float, default=15)
    arguments = parser.parse_args()
    if arguments.max_boundary_gap_seconds <= 0:
        parser.error('A margem máxima deve ser positiva')
    with arguments.input.open(encoding='utf-8') as source:
        samples = [json.loads(line) for line in source if line.strip()]
    window = None
    if arguments.measurement_summary:
        with arguments.measurement_summary.open(encoding='utf-8') as source:
            window = json.load(source)
    result = summarize(samples, window, arguments.max_boundary_gap_seconds)
    with arguments.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write('\n')


if __name__ == '__main__':
    main()
