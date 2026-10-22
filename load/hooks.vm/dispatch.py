#!/usr/bin/env python3
import base64
import csv
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from criar_manifesto import build_manifest

SOCKET = '/run/tcc-experiment/session.sock'
SERVICES = ('app', 'postgres', 'redis')


def remote(service, action, *values):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(1800)
        connection.connect(SOCKET)
        request = {'service': service, 'action': action, 'values': list(values)}
        connection.sendall(json.dumps(request).encode() + b'\n')
        with connection.makefile('rb') as response_file:
            response = json.loads(response_file.readline())
    if not response['ok']:
        raise RuntimeError(response['error'])
    return response['value']


def verify_manifest():
    response = remote('postgres', 'verify')
    rows = csv.DictReader(io.StringIO(base64.b64decode(response['csv']).decode()))
    actual = build_manifest(rows, 'base-v1')
    expected = json.loads(Path(os.environ['MANIFEST_PATH']).read_text())
    if actual != expected:
        raise ValueError('Base restaurada diferente do manifesto')
    status = remote('app', 'status')
    if not status['running'] or status['cache_mode'] != os.environ['CACHE_MODE'] or '/tcc_experimento?' not in status['database_url']:
        raise ValueError('API fora da configuração experimental solicitada')
    return {'cache_mode': status['cache_mode'], 'base_matches_manifest': True, 'reserved_orders_open': True}


def remote_run_id():
    campaign = str(Path(os.environ['RUN_DIR']).resolve().parent)
    return os.environ['RUN_ID'] + '-' + hashlib.sha256(campaign.encode()).hexdigest()[:10]


def monitor_start():
    run_id = remote_run_id()
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(lambda service: remote(service, 'monitor-start', run_id), SERVICES))
        if not all(result['monitoring_ready'] for result in results):
            raise ValueError('Monitoramento incompleto')
    except BaseException:
        for service in SERVICES:
            try:
                remote(service, 'monitor-stop', run_id, 0)
            except (RuntimeError, ValueError, subprocess.SubprocessError):
                pass
        raise
    return {'monitoring_ready': True, 'services': list(SERVICES)}


def monitor_stop():
    run_id = remote_run_id()
    summary_path = Path(os.environ['MEASUREMENT_SUMMARY'])
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else None
    completed = summary['measurement_completed_unix_ms'] if summary else 0
    failures = []
    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {service: executor.submit(remote, service, 'monitor-stop', run_id, completed) for service in SERVICES}
        for service, future in futures.items():
            try:
                results[service] = future.result()
            except BaseException as error:
                failures.append(str(error))
    if failures:
        raise RuntimeError('; '.join(failures))
    if summary is None:
        raise ValueError('Coletores encerrados, mas resumo de medição ausente')
    directory = Path(os.environ['RUN_DIR']) / 'monitoring'
    summarizer = Path(__file__).resolve().parents[2] / 'monitoring/resumir.py'
    for service, result in results.items():
        source = directory / f'{service}.jsonl'
        source.write_bytes(base64.b64decode(result['jsonl']))
        destination = directory / f'{service}-summary.json'
        subprocess.run([sys.executable, str(summarizer), str(source), '--measurement-summary', str(summary_path), '--output', str(destination)], check=True, stdout=sys.stderr)
    return {'monitoring_stopped': True}


def restore():
    remote('app', 'stop')
    result = remote('postgres', 'restore', os.environ['BACKUP_SHA256'])
    return {'backup_sha256': result['backup_sha256'], 'manifest_sha256': os.environ['MANIFEST_SHA256']}


def main():
    hook = Path(sys.argv[0]).name
    operations = {'restore': restore, 'mode': lambda: {'cache_mode': remote('app', 'mode', os.environ['CACHE_MODE'])['cache_mode']},
                  'clear': lambda: {'cache_empty': remote('redis', 'clear')['cache_empty']}, 'verify': verify_manifest,
                  'monitor-start': monitor_start, 'monitor-stop': monitor_stop}
    if hook not in operations:
        raise ValueError('Executar pelo nome do hook')
    result = operations[hook]()
    print(json.dumps({'hook': hook, 'completed': True, **result}))


if __name__ == '__main__':
    main()
