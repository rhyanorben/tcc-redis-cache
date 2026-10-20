#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from planejar import K6_IMAGE, PROFILES, VIRTUAL_USERS

HOOKS = ('restore', 'mode', 'clear', 'verify', 'monitor-start', 'monitor-stop')
SERVICES = ('app', 'postgres', 'redis')


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_plan(plan, manifest_path):
    if plan.get('schema_version') != 1 or plan.get('k6_image') != K6_IMAGE:
        raise ValueError('Plano ou imagem k6 incompatíveis.')
    if plan.get('active_companies') != 25 or plan.get('warmup_seconds') != 120 or plan.get('measurement_seconds') != 300:
        raise ValueError('Tempos ou empresas ativas incompatíveis.')
    if file_hash(manifest_path) != plan.get('manifest_sha256'):
        raise ValueError('O manifesto foi alterado desde a criação do plano.')
    pairs = {}
    identifiers = set()
    if len(plan.get('runs', [])) != 200:
        raise ValueError('O plano definitivo deve conter exatamente 200 execuções.')
    for index, run in enumerate(plan['runs'], start=1):
        if run['sequence'] != index or run['run_id'] in identifiers or not re.fullmatch(r'[A-Za-z0-9_-]+', run['run_id']):
            raise ValueError('Sequência ou identificador de execução inválido.')
        identifiers.add(run['run_id'])
        if run['profile'] not in PROFILES or run['virtual_users'] not in VIRTUAL_USERS or run['repetition'] not in range(1, 6):
            raise ValueError('Cenário fora da matriz experimental.')
        if run['cache_mode'] not in ('on', 'off') or not re.fullmatch(r'[a-f0-9]{16}', run['seed']):
            raise ValueError('Modo ou semente inválidos.')
        key = (run['profile'], run['virtual_users'], run['repetition'])
        pair = pairs.setdefault(key, [])
        pair.append((run['cache_mode'], run['seed'], run['pair_id']))
    if len(pairs) != 100:
        raise ValueError('Matriz incompleta.')
    for pair in pairs.values():
        if sorted(entry[0] for entry in pair) != ['off', 'on'] or len({entry[1:] for entry in pair}) != 1:
            raise ValueError('Pares precisam ter os dois modos e a mesma semente.')


def validate_url(value):
    parsed = urlparse(value)
    if parsed.scheme != 'http' or parsed.hostname not in ('10.10.10.10', '10.20.20.10', 'localhost', '127.0.0.1'):
        raise ValueError('Destino HTTP fora da lista permitida.')
    if parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('BASE_URL deve conter somente protocolo, host e porta.')
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError('Porta inválida.')
    return value.rstrip('/')


def validate_hooks(directory):
    if directory is None:
        raise ValueError('--hooks é obrigatório para executar. Exemplos não são implementações.')
    for name in HOOKS:
        path = directory / name
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f'Hook ausente ou não executável: {path}')


def run_hook(directory, name, environment, expected):
    receipt_path = Path(environment['RUN_DIR']) / f'hook-{name}.json'
    log_path = Path(environment['RUN_DIR']) / f'hook-{name}.stderr.log'
    with log_path.open('w', encoding='utf-8') as error_log:
        result = subprocess.run([str((directory / name).resolve())], env=environment, text=True,
                                stdout=subprocess.PIPE, stderr=error_log, check=True)
    receipt = json.loads(result.stdout)
    if receipt.get('hook') != name or receipt.get('completed') is not True:
        raise ValueError(f'Hook {name} não confirmou conclusão.')
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise ValueError(f'Hook {name}: confirmação divergente para {key}.')
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')


def run_k6(root, run_directory, manifest_path, phase, environment):
    summary_name = 'warmup-summary.json' if phase == 'warmup' else 'measurement-summary.json'
    command = [
        'docker', 'run', '--rm', '--network', 'host', '--read-only',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--user', f'{os.getuid()}:{os.getgid()}',
        '--mount', f'type=bind,source={root},target=/scripts,readonly',
        '--mount', f'type=bind,source={manifest_path},target=/data/manifesto.json,readonly',
        '--mount', f'type=bind,source={run_directory},target=/results',
        K6_IMAGE, 'run', '--quiet',
    ]
    values = {
        'BASE_URL': environment['BASE_URL'], 'RUN_ID': environment['RUN_ID'],
        'PROFILE': environment['PROFILE'], 'VUS': environment['VUS'],
        'SEED': environment['SEED'], 'CACHE_MODE': environment['CACHE_MODE'],
        'MANIFEST': '/data/manifesto.json', 'PHASE': phase,
        'SUMMARY_PATH': f'/results/{summary_name}',
    }
    for key, value in values.items():
        command.extend(['-e', f'{key}={value}'])
    command.append('/scripts/experiment.js')
    with (run_directory / f'k6-{phase}.log').open('w', encoding='utf-8') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    summary = json.loads((run_directory / summary_name).read_text(encoding='utf-8'))
    if summary.get('valid') is not True or summary.get('phase') != phase:
        raise ValueError(f'Resumo k6 inválido em {phase}.')
    if phase == 'measurement' and summary.get('requests', 0) <= 0:
        raise ValueError('A medição não registrou requisições.')
    if phase == 'measurement' and summary.get('valid_for_campaign') is not True:
        raise ValueError('Smoke ou medição incompleta não podem compor a campanha.')
    return summary


def validate_monitoring(run_directory, summary):
    for service in SERVICES:
        path = run_directory / 'monitoring' / f'{service}-summary.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('scope') != 'measurement_resources_with_bracketed_counters' or data.get('service') != service:
            raise ValueError(f'Resumo de monitoramento incompatível: {service}.')
        window = data.get('measurement_window', {})
        for key in ('measurement_start_unix_ms', 'measurement_end_unix_ms', 'measurement_completed_unix_ms'):
            if window.get(key) != summary[key]:
                raise ValueError(f'Janela de monitoramento divergente: {service}/{key}.')


def execute_run(plan, run, arguments, manifest_path, backup_hash):
    run_directory = arguments.saida.resolve() / run['run_id']
    run_directory.mkdir(parents=True, exist_ok=False)
    (run_directory / 'monitoring').mkdir()
    (run_directory / 'run.json').write_text(json.dumps(run, indent=2) + '\n', encoding='utf-8')
    environment = os.environ.copy()
    environment.update({
        'RUN_ID': run['run_id'], 'RUN_DIR': str(run_directory),
        'PROFILE': run['profile'], 'VUS': str(run['virtual_users']),
        'SEED': run['seed'], 'CACHE_MODE': run['cache_mode'],
        'BASE_URL': arguments.base_url,
        'MANIFEST_PATH': str(manifest_path), 'MANIFEST_SHA256': plan['manifest_sha256'],
        'BACKUP_PATH': str(arguments.backup.resolve()), 'BACKUP_SHA256': backup_hash,
        'MEASUREMENT_SUMMARY': str(run_directory / 'measurement-summary.json'),
    })
    monitoring = False
    try:
        run_hook(arguments.hooks, 'restore', environment,
                 {'backup_sha256': backup_hash, 'manifest_sha256': plan['manifest_sha256']})
        run_hook(arguments.hooks, 'mode', environment, {'cache_mode': run['cache_mode']})
        run_hook(arguments.hooks, 'clear', environment, {'cache_empty': True})
        run_hook(arguments.hooks, 'verify', environment,
                 {'cache_mode': run['cache_mode'], 'base_matches_manifest': True, 'reserved_orders_open': True})
        run_k6(Path(__file__).resolve().parent, run_directory, manifest_path, 'warmup', environment)
        monitoring = True
        run_hook(arguments.hooks, 'monitor-start', environment,
                 {'monitoring_ready': True, 'services': list(SERVICES)})
        summary = run_k6(Path(__file__).resolve().parent, run_directory, manifest_path, 'measurement', environment)
        run_hook(arguments.hooks, 'monitor-stop', environment, {'monitoring_stopped': True})
        monitoring = False
        validate_monitoring(run_directory, summary)
        (run_directory / 'complete.json').write_text(json.dumps({
            'complete': True, 'backup_sha256': backup_hash, 'manifest_sha256': plan['manifest_sha256'],
        }, indent=2) + '\n', encoding='utf-8')
    except BaseException as error:
        (run_directory / 'invalid.json').write_text(json.dumps({'valid': False, 'error': str(error)}) + '\n', encoding='utf-8')
        raise
    finally:
        if monitoring:
            try:
                run_hook(arguments.hooks, 'monitor-stop', environment, {'monitoring_stopped': True})
            except (ValueError, OSError, subprocess.SubprocessError):
                print(f'Falha ao encerrar monitoramento em {run_directory}; verifique os processos.', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='Exibe o plano por padrão. --executar autoriza os hooks informados e a carga.')
    parser.add_argument('--plano', type=Path, required=True)
    parser.add_argument('--manifesto', type=Path)
    parser.add_argument('--saida', type=Path)
    parser.add_argument('--hooks', type=Path)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--backup-sha256')
    parser.add_argument('--base-url', default='http://10.10.10.10:8080')
    parser.add_argument('--limite', type=int, help='Executa somente os primeiros N casos; não equivale à campanha completa.')
    parser.add_argument('--executar', action='store_true')
    arguments = parser.parse_args()
    try:
        plan = json.loads(arguments.plano.read_text(encoding='utf-8'))
        manifest_path = (arguments.manifesto or Path(plan['manifest_path'])).resolve()
        validate_plan(plan, manifest_path)
        arguments.base_url = validate_url(arguments.base_url)
        if arguments.limite is not None and not 1 <= arguments.limite <= 200:
            raise ValueError('--limite precisa estar entre 1 e 200.')
        runs = plan['runs'][:arguments.limite]
        if not arguments.executar:
            print(json.dumps({'mode': 'PREVIEW', 'runs': runs, 'hooks_order': list(HOOKS),
                              'manifest_sha256': plan['manifest_sha256'],
                              'notice': 'Nenhum hook, Docker, conexão ou carga executados.'}, indent=2))
            return
        validate_hooks(arguments.hooks)
        if arguments.backup is None or not arguments.backup.is_file() or arguments.backup.stat().st_size == 0:
            raise ValueError('É obrigatório informar um backup não vazio e validado para restauração.')
        if not arguments.backup_sha256 or not re.fullmatch('[a-f0-9]{64}', arguments.backup_sha256):
            raise ValueError('--backup-sha256 deve ser o hash previamente conferido do backup.')
        backup_hash = file_hash(arguments.backup)
        if backup_hash != arguments.backup_sha256:
            raise ValueError('O backup não corresponde ao SHA-256 informado.')
        if arguments.saida is None:
            raise ValueError('--saida é obrigatório para executar.')
        arguments.saida.mkdir(parents=True, exist_ok=False)
        (arguments.saida / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
        for run in runs:
            print(f"Execução {run['sequence']}/200: {run['run_id']}", flush=True)
            execute_run(plan, run, arguments, manifest_path, backup_hash)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Execução interrompida: {error}\n')


if __name__ == '__main__':
    main()
