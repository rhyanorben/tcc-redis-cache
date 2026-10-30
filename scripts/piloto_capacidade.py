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


def selected_pair(plan):
    pair = [run for run in plan['runs'] if run['profile'] == '90-10' and run['virtual_users'] == 500 and run['repetition'] == 4]
    if len(pair) != 2 or [run['sequence'] for run in pair] != [11, 12] or pair[0]['pair_id'] != pair[1]['pair_id'] or pair[0]['seed'] != pair[1]['seed'] or {run['cache_mode'] for run in pair} != {'on', 'off'}:
        raise ValueError('O plano precisa conter o par original 90-10, 500 usuários, repetição 4, nas posições 11 e 12')
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


def execute_pilot(campaign, token):
    if CONFIG['protocol_version'] != 2 or campaign.resolve() != Path(CONFIG['campaign']).resolve():
        raise ValueError('O piloto deve usar somente a campanha v2 configurada')
    plan = blocos.read(campaign / 'plan.json')
    pair = selected_pair(plan)
    root = campaign.parent / 'piloto-capacidade-v2'
    attempt = root / ('tentativa-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    attempt.mkdir(parents=True, exist_ok=False)
    state = {'eligible_for_campaign': False, 'excluded_from_campaign': True, 'campaign': str(campaign), 'runs': pair, 'status': 'authenticating',
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
            for run in pair:
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
        blocos.summarize_generator(attempt, pair)
        state.update(status='complete', completed_runs=[run['run_id'] for run in pair])
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
    arguments = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('O piloto na geradora deve ser iniciado com sudo')
    directory = Path('/run/tcc-experiment')
    directory.mkdir(mode=0o700, exist_ok=True)
    with (directory / 'campaign.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        signal.signal(signal.SIGTERM, blocos.interrupted)
        signal.signal(signal.SIGHUP, blocos.interrupted)
        execute_pilot(arguments.campanha, arguments.host_token)


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print('Piloto interrompido: ' + str(error), file=sys.stderr)
        sys.exit(1)
