#!/usr/bin/env python3
import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from executar import validate_monitoring


def statistics_for(values):
    return {
        'n': len(values),
        'mean': statistics.mean(values),
        'median': statistics.median(values),
        'sample_standard_deviation': statistics.stdev(values) if len(values) > 1 else 0,
        'minimum': min(values),
        'maximum': max(values),
    }


def flatten_numeric(value, prefix=''):
    result = {}
    if isinstance(value, dict):
        for name, item in value.items():
            child = f'{prefix}.{name}' if prefix else name
            result.update(flatten_numeric(item, child))
    elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        result[prefix] = value
    return result


def run_metrics(directory, summary):
    metrics = {}
    for name in ('reads', 'writes', 'requests', 'errors', 'read_errors', 'write_errors',
                 'throughput_requests_per_second', 'error_ratio', 'observed_write_ratio',
                 'read_latency_ms', 'write_latency_ms'):
        metrics.update(flatten_numeric(summary.get(name), name))
    monitoring_paths = [directory / 'monitoring' / f'{service}-summary.json' for service in ('app', 'postgres', 'redis')]
    present = [path.is_file() for path in monitoring_paths]
    if not all(present):
        raise ValueError(f'Monitoramento obrigatório ausente ou parcial em {directory}.')
    if all(present):
        validate_monitoring(directory, summary)
        for path in monitoring_paths:
            monitor = json.loads(path.read_text(encoding='utf-8'))
            service = monitor['service']
            for name in ('docker_cpu_percent', 'docker_memory_bytes'):
                values = monitor.get(name)
                if not isinstance(values, dict) or set(values) != {'mean', 'minimum', 'maximum'}:
                    raise ValueError(f'Métrica de recursos ausente ou inválida: {service}/{name}.')
                numbers = flatten_numeric(values, f'{service}.resources.{name}')
                if len(numbers) != 3:
                    raise ValueError(f'Métrica de recursos não finita: {service}/{name}.')
                metrics.update(numbers)
            if service == 'app':
                metrics.update(flatten_numeric(monitor.get('application'), 'app.application'))
            elif service == 'postgres':
                metrics.update(flatten_numeric(monitor.get('postgres', {}).get('totals'), 'postgres.totals'))
            else:
                redis = monitor.get('redis', {})
                for name in ('counters', 'used_memory', 'used_memory_dataset', 'used_memory_rss'):
                    metrics.update(flatten_numeric(redis.get(name), f'redis.{name}'))
    return metrics


def load_runs(results_directory):
    runs = {}
    for path in sorted(results_directory.glob('*/measurement-summary.json')):
        directory = path.parent
        if (directory / 'invalid.json').exists():
            raise ValueError(f'Execução inválida presente: {directory}. Separe-a antes de consolidar.')
        if not (directory / 'complete.json').is_file():
            raise ValueError(f'Execução sem confirmação de conclusão: {directory}.')
        completion = json.loads((directory / 'complete.json').read_text(encoding='utf-8'))
        if completion.get('complete') is not True:
            raise ValueError(f'Confirmação de conclusão inválida: {directory}.')
        summary = json.loads(path.read_text(encoding='utf-8'))
        run = json.loads((directory / 'run.json').read_text(encoding='utf-8'))
        if summary.get('scope') != 'measurement_only' or summary.get('valid') is not True:
            raise ValueError(f'Resumo inválido em {directory}.')
        if summary.get('smoke_test') is not False or summary.get('valid_for_campaign') is not True:
            raise ValueError(f'Smoke ou resumo sem validação de campanha em {directory}.')
        start = summary.get('measurement_start_unix_ms', 0)
        end = summary.get('measurement_end_unix_ms', 0)
        completed = summary.get('measurement_completed_unix_ms', 0)
        if summary.get('nominal_measurement_seconds') != 300 or end - start != 300000 or completed < end:
            raise ValueError(f'Janela de medição incompatível em {directory}.')
        for name in ('run_id', 'profile', 'virtual_users', 'seed', 'cache_mode'):
            if run[name] != summary.get(name):
                raise ValueError(f'Resumo diverge de run.json: {directory}/{name}.')
        key = (run['profile'], run['virtual_users'], run['cache_mode'], run['repetition'])
        if key in runs:
            raise ValueError(f'Repetição duplicada: {key}.')
        runs[key] = {
            'run': run, 'completion': completion,
            'metrics': run_metrics(directory, summary),
        }
    if not runs:
        raise ValueError('Nenhum resultado completo encontrado.')
    return runs


def consolidate(runs):
    grouped = defaultdict(dict)
    for (profile, users, mode, repetition), result in runs.items():
        grouped[(profile, users, mode)][repetition] = result
    for key, repetitions in grouped.items():
        if set(repetitions) != set(range(1, 6)):
            raise ValueError(f'{key}: são necessárias cinco repetições completas.')
    groups = []
    pairs = []
    for (profile, users, mode), repetitions in sorted(grouped.items()):
        names = set.intersection(*(set(result['metrics']) for result in repetitions.values()))
        if any(set(result['metrics']) != names for result in repetitions.values()):
            raise ValueError(f'{profile}/{users}/{mode}: métricas diferentes entre repetições.')
        groups.append({
            'profile': profile, 'virtual_users': users, 'cache_mode': mode,
            'metrics': {name: statistics_for([repetitions[index]['metrics'][name] for index in range(1, 6)])
                        for name in sorted(names)},
        })
    scenarios = sorted({(profile, users) for profile, users, mode in grouped})
    for profile, users in scenarios:
        if (profile, users, 'on') not in grouped or (profile, users, 'off') not in grouped:
            raise ValueError(f'{profile}/{users}: faltam resultados em um dos modos.')
        on = grouped[(profile, users, 'on')]
        off = grouped[(profile, users, 'off')]
        for repetition in range(1, 6):
            left = on[repetition]
            right = off[repetition]
            if left['run']['seed'] != right['run']['seed'] or left['run']['pair_id'] != right['run']['pair_id']:
                raise ValueError('Resultados não pareados por semente e identificador.')
            if left['completion'] != right['completion']:
                raise ValueError('Resultados pareados usam backups ou manifestos diferentes.')
        names = set.intersection(*(set(result['metrics']) for result in list(on.values()) + list(off.values())))
        paired_metrics = {}
        for name in sorted(names):
            differences = [on[index]['metrics'][name] - off[index]['metrics'][name] for index in range(1, 6)]
            percentages = [100 * (on[index]['metrics'][name] - off[index]['metrics'][name]) / off[index]['metrics'][name]
                           for index in range(1, 6) if off[index]['metrics'][name] != 0]
            paired_metrics[name] = {
                'difference_on_minus_off': statistics_for(differences),
                'percent_on_minus_off_over_off': statistics_for(percentages) if len(percentages) == 5 else None,
                'percent_unavailable_reason': 'baseline_zero' if len(percentages) < 5 else None,
            }
        unpaired = set(on[1]['metrics']) ^ set(off[1]['metrics'])
        pairs.append({'profile': profile, 'virtual_users': users, 'metrics': paired_metrics,
                      'metrics_unavailable_in_one_mode': sorted(unpaired)})
    return {
        'schema_version': 1,
        'scope': 'five_repetitions_per_mode_and_paired_differences',
        'percent_definition': '100 * (cache_on - cache_off) / cache_off, calculado por par antes de resumir',
        'latency_note': 'A média dos p95/p99 das repetições não é o percentil global das requisições.',
        'monitoring_note': 'CPU/memória: estatísticas por execução; contadores: deltas delimitados pelas amostras externas à janela.',
        'groups': groups,
        'pairs': pairs,
    }


def main():
    parser = argparse.ArgumentParser(description='Consolida cinco repetições em ambos os modos; não executa carga.')
    parser.add_argument('--resultados', type=Path, required=True)
    parser.add_argument('--saida', type=Path, required=True)
    arguments = parser.parse_args()
    try:
        result = consolidate(load_runs(arguments.resultados))
        arguments.saida.mkdir(parents=True, exist_ok=False)
        (arguments.saida / 'summary.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        with (arguments.saida / 'groups.csv').open('w', newline='', encoding='utf-8') as output:
            fields = ['profile', 'virtual_users', 'cache_mode', 'metric', 'n', 'mean', 'median',
                      'sample_standard_deviation', 'minimum', 'maximum']
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for group in result['groups']:
                for name, values in group['metrics'].items():
                    writer.writerow({**{key: group[key] for key in fields[:3]}, 'metric': name, **values})
        with (arguments.saida / 'paired.csv').open('w', newline='', encoding='utf-8') as output:
            fields = ['profile', 'virtual_users', 'metric', 'statistic', 'n', 'mean', 'median',
                      'sample_standard_deviation', 'minimum', 'maximum']
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for pair in result['pairs']:
                for name, values in pair['metrics'].items():
                    for statistic in ('difference_on_minus_off', 'percent_on_minus_off_over_off'):
                        if values[statistic] is not None:
                            writer.writerow({'profile': pair['profile'], 'virtual_users': pair['virtual_users'],
                                             'metric': name, 'statistic': statistic, **values[statistic]})
        print(f'Consolidação gerada em {arguments.saida}.')
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'Consolidação interrompida: {error}\n')


if __name__ == '__main__':
    main()
