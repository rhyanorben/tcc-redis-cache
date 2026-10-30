#!/usr/bin/env python3
import argparse
import fcntl
import json
import os
import signal
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'load'))
import blocos
import executar
from recursos_bloco import Resources

CONFIG = blocos.CONFIG


def selected_pair(plan, profile='90-10'):
    pair = [run for run in plan['runs'] if run['profile'] == profile and run['virtual_users'] == 500 and run['repetition'] == 4]
    if len(pair) != 2 or pair[1]['sequence'] != pair[0]['sequence'] + 1 or pair[0]['pair_id'] != pair[1]['pair_id'] or pair[0]['seed'] != pair[1]['seed'] or {run['cache_mode'] for run in pair} != {'on', 'off'}:
        raise ValueError(f'O plano precisa conter o par consecutivo {profile}, 500 usuários, repetição 4')
    return pair


def package(root):
    exports = root / 'exports'
    exports.mkdir(parents=True, exist_ok=True)
    destination = exports / 'piloto-capacidade.zip'
    files = sorted(path for path in root.rglob('*') if path.is_file() and exports not in path.parents)
    inventory = {str(path.relative_to(root)): executar.file_hash(path) for path in files}
    temporary = destination.with_suffix('.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, str(path.relative_to(root)))
        archive.writestr('SHA256.json', json.dumps(inventory, indent=2))
    temporary.replace(destination)
    destination.with_suffix('.zip.sha256').write_text(executar.file_hash(destination) + '  ' + destination.name + '\n')
    print('Piloto preservado em: ' + str(destination), flush=True)


def execute_pilot(campaign, token, read_only=False):
    if CONFIG['protocol_version'] != 3 or campaign.resolve() != Path(CONFIG['campaign']).resolve():
        raise ValueError('O piloto deve usar somente a campanha de paginação v3 configurada')
    plan = blocos.read(campaign / 'plan.json')
    pair = selected_pair(plan, '100-0' if read_only else '90-10')
    runs = [run for run in pair if run['cache_mode'] == 'on'] if read_only else pair
    root = campaign.parent / ('piloto-leitura-v3' if read_only else 'piloto-capacidade-v3')
    attempt = root / ('tentativa-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    attempt.mkdir(parents=True, exist_ok=False)
    state = {'eligible_for_campaign': False, 'excluded_from_campaign': True, 'campaign': str(campaign), 'runs': runs, 'status': 'authenticating',
             'purpose': 'read-only-generator-capacity' if read_only else 'paired-generator-capacity',
             'started_at': datetime.now(timezone.utc).isoformat(), 'protocol_version': CONFIG['protocol_version'],
             'script_sha256': executar.file_hash(Path(__file__)), 'campaign_metadata': blocos.read(campaign / 'campaign.json')}
    blocos.write(attempt / 'pilot.json', state)
    blocos.write(attempt / 'plan.json', plan)
    (attempt / 'manifesto.json').write_bytes((campaign / 'manifesto.json').read_bytes())
    broker = None
    failure = None
    try:
        broker = blocos.session_start(lifetime_seconds=7200)
        blocos.write(attempt / 'preflight.json', blocos.preflight(campaign, token))
        state['status'] = 'running'
        blocos.write(attempt / 'pilot.json', state)
        arguments = SimpleNamespace(saida=attempt, hooks=PROJECT / 'load/hooks.vm', base_url=CONFIG['base_url'], backup=Path(CONFIG['backup']))
        resources = Resources(attempt / 'gerador.jsonl', token)
        resources.start()
        run_error = None
        try:
            for run in runs:
                print(f"Piloto de capacidade — execução original {run['sequence']}/200: {run['run_id']}", flush=True)
                executar.execute_run(plan, run, arguments, campaign / 'manifesto.json', CONFIG['backup_sha256'])
        except BaseException as error:
            run_error = error
            raise
        finally:
            try:
                resources.close()
            except Exception as error:
                blocos.write(attempt / 'generator-close-error.json', {'error': str(error)})
                if run_error is None:
                    raise
        blocos.summarize_generator(attempt, runs)
        state.update(status='complete', completed_runs=[run['run_id'] for run in runs])
    except BaseException as error:
        failure = error
        state.update(status='interrupted', error=str(error))
        raise
    finally:
        try:
            if broker:
                try:
                    blocos.session_stop(broker)
                except Exception as error:
                    blocos.write(attempt / 'session-close-error.json', {'error': str(error)})
                    state.update(status='interrupted', cleanup_error=str(error))
                    if failure is None:
                        raise
        finally:
            state['ended_at'] = datetime.now(timezone.utc).isoformat()
            blocos.write(attempt / 'pilot.json', state)
            package(root)
    print('Piloto concluído; este pacote não integra a campanha. Nenhum bloco foi iniciado.', flush=True)


def main():
    parser = argparse.ArgumentParser(description='Executa manualmente o par de capacidade 90-10/500; não integra a campanha.')
    parser.add_argument('--campanha', type=Path, default=Path(CONFIG['campaign']))
    parser.add_argument('--host-token', required=True)
    parser.add_argument('--somente-leitura', action='store_true', help='Valida somente 100/0 com cache e 500 VUs, fora da campanha.')
    arguments = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('O piloto na geradora deve ser iniciado com sudo')
    directory = Path('/run/tcc-experiment')
    directory.mkdir(mode=0o700, exist_ok=True)
    with (directory / 'campaign.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        signal.signal(signal.SIGTERM, blocos.interrupted)
        signal.signal(signal.SIGHUP, blocos.interrupted)
        execute_pilot(arguments.campanha, arguments.host_token, arguments.somente_leitura)


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print('Piloto interrompido: ' + str(error), file=sys.stderr)
        sys.exit(1)
