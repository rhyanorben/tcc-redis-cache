#!/usr/bin/env python3
import argparse
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SQL_STATISTICS = """
SELECT json_build_object(
    'postmaster_start_time', pg_postmaster_start_time(),
    'stats_reset', (SELECT stats_reset FROM public.pg_stat_statements_info),
    'dealloc', (SELECT dealloc FROM public.pg_stat_statements_info),
    'statements', coalesce(json_agg(json_build_object(
        'queryid', queryid::text, 'query', query, 'calls', calls, 'rows', rows,
        'total_exec_time', total_exec_time,
        'shared_blks_hit', shared_blks_hit, 'shared_blks_read', shared_blks_read,
        'shared_blks_dirtied', shared_blks_dirtied, 'shared_blks_written', shared_blks_written
    )), '[]'::json)
)
FROM public.pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
AND userid = (SELECT oid FROM pg_roles WHERE rolname = 'tcc_app')
"""

CACHE_COUNTERS = ('tcc.cache.errors', 'tcc.cache.invalidations', 'tcc.cache.discarded_writes')
REDIS_FIELDS = ('run_id', 'uptime_in_seconds', 'used_memory', 'used_memory_dataset', 'used_memory_rss',
                'maxmemory', 'maxmemory_policy', 'keyspace_hits', 'keyspace_misses', 'evicted_keys',
                'expired_keys', 'total_error_replies', 'total_commands_processed')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def execute(arguments):
    result = subprocess.run(arguments, text=True, capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError(f'{arguments[0]} terminou com código {result.returncode}')
    return result.stdout.strip()


def compose_command(compose_file, arguments):
    command = ['docker', 'compose', '--project-directory', str(compose_file.parent)]
    environment_file = compose_file.parent / '.env'
    if environment_file.is_file():
        command.extend(['--env-file', str(environment_file)])
    return command + ['-f', str(compose_file), *arguments]


def docker_statistics(compose_file, service):
    container_id = execute(compose_command(compose_file, ['ps', '-q', service]))
    if not container_id or '\n' in container_id:
        raise RuntimeError('Era esperado exatamente um contêiner em execução')
    return json.loads(execute(['docker', 'stats', '--no-stream', '--format', '{{json .}}', container_id]))


def read_json(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def metric_value(base_url, name, tag=None):
    query = '' if tag is None else '?' + urllib.parse.urlencode({'tag': tag})
    data = read_json(base_url.rstrip('/') + '/actuator/metrics/' + name + query)
    return sum(item['value'] for item in data['measurements'])


def app_statistics(base_url):
    available = set(read_json(base_url.rstrip('/') + '/actuator/metrics')['names'])
    result = {'cache_instrumented': 'tcc.cache.requests' in available,
              'process_start_time': metric_value(base_url, 'process.start.time')}
    for outcome in ('hit', 'miss', 'fallback'):
        result['tcc.cache.requests.' + outcome] = (
            metric_value(base_url, 'tcc.cache.requests', 'result:' + outcome)
            if result['cache_instrumented'] else 0)
    for name in CACHE_COUNTERS:
        result[name] = metric_value(base_url, name) if name in available else 0
    return result


def postgres_statistics(compose_file):
    arguments = ['exec', '-T', 'postgres', 'psql', '-X', '-At', '-v', 'ON_ERROR_STOP=1',
                 '-U', 'tcc_monitor', '-d', 'tcc', '-c', SQL_STATISTICS]
    return json.loads(execute(compose_command(compose_file, arguments)))


def redis_statistics(compose_file):
    arguments = ['exec', '-T', 'redis', 'sh', '-c',
                 'REDISCLI_AUTH="$(cat /run/secrets/redis_password)" redis-cli --no-auth-warning --raw INFO all']
    fields = {}
    for line in execute(compose_command(compose_file, arguments)).splitlines():
        if ':' not in line or line.startswith('#'):
            continue
        key, value = line.split(':', 1)
        if key in REDIS_FIELDS:
            fields[key] = int(value) if value.isdigit() else value
    if 'run_id' not in fields:
        raise RuntimeError('Redis INFO não retornou identificação do processo')
    return fields


def collect(service, compose_file, base_url):
    result = {'docker': docker_statistics(compose_file, service)}
    if service == 'app':
        result['application'] = app_statistics(base_url)
    elif service == 'postgres':
        result['postgres'] = postgres_statistics(compose_file)
    else:
        result['redis'] = redis_statistics(compose_file)
    return result


def parse_arguments():
    parser = argparse.ArgumentParser(description='Amostra recursos e contadores na própria VM do serviço.')
    parser.add_argument('--service', choices=('app', 'postgres', 'redis'), required=True)
    parser.add_argument('--compose', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=360)
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--delay', type=float, default=0)
    parser.add_argument('--management-url', default='http://127.0.0.1:8081')
    arguments = parser.parse_args()
    if arguments.duration <= 0 or arguments.interval <= 0 or arguments.delay < 0:
        parser.error('Duração e intervalo devem ser positivos; atraso não pode ser negativo')
    arguments.compose = arguments.compose.resolve()
    if not arguments.compose.is_file():
        parser.error('Compose não encontrado')
    return arguments


def main():
    arguments = parse_arguments()
    failed = False
    with arguments.output.open('x', encoding='utf-8') as output:
        time.sleep(arguments.delay)
        start = time.monotonic()
        deadline = start + arguments.duration
        next_sample = start
        while True:
            time.sleep(max(0, next_sample - time.monotonic()))
            sample = {'timestamp': utc_now(), 'elapsed_seconds': time.monotonic() - start,
                      'service': arguments.service}
            try:
                sample.update(collect(arguments.service, arguments.compose, arguments.management_url))
            except (RuntimeError, OSError, ValueError, urllib.error.URLError, subprocess.TimeoutExpired) as error:
                sample['error'] = type(error).__name__ + ': ' + str(error)
                failed = True
            sample['completed_at'] = utc_now()
            output.write(json.dumps(sample, ensure_ascii=False) + '\n')
            output.flush()
            if next_sample >= deadline:
                break
            next_sample = min(max(next_sample + arguments.interval, time.monotonic()), deadline)
    if failed:
        raise SystemExit('Coleta incompleta: consulte os erros registrados no JSONL')


if __name__ == '__main__':
    main()
