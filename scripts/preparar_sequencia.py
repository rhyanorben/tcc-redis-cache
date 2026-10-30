#!/usr/bin/env python3
import argparse
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
FILES = ('load/blocos.py', 'load/intervalo_blocos.py', 'load/recursos_bloco.py')
LOCK = Path('/run/tcc-experiment/campaign.lock')
MISSING_BACKUP = "'types.SimpleNamespace' object has no attribute 'backup'"


def fingerprint(project):
    paths = [path for folder in ('load', 'monitoring', 'infra/experiment') for path in (project / folder).rglob('*')
             if path.suffix in ('.py', '.js', '.json') and '__pycache__' not in path.parts and 'tests' not in path.parts]
    return {str(path.relative_to(project)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def failed_before_restore(campaign):
    try:
        blocks = campaign / 'blocks'
        directory = blocks / 'bloco-01'
        if set(blocks.iterdir()) != {directory}:
            return False
        interruptions = list(directory.glob('interruption-*.json'))
        if not interruptions or any(json.loads(path.read_text()).get('error') != MISSING_BACKUP for path in interruptions):
            return False
        first = json.loads((campaign / 'plan.json').read_text())['runs'][0]
        attempts = list((directory / first['pair_id']).glob('tentativa-*'))
        if not attempts or len(attempts) != len(interruptions):
            return False
        allowed = {directory / 'preflight.json', directory / 'preflight-par-1.json', *interruptions}
        for attempt in attempts:
            run = attempt / first['run_id'] / 'run.json'
            if json.loads(run.read_text()) != first:
                return False
            allowed.update((run, attempt / 'gerador.jsonl'))
        return all(path in allowed for path in blocks.rglob('*') if path.is_file())
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return False


def failed_during_generator_transition(campaign):
    try:
        blocks = campaign / 'blocks'
        directory = blocks / 'bloco-01'
        if set(blocks.iterdir()) != {directory}:
            return False
        plan = json.loads((campaign / 'plan.json').read_text())
        pair = plan['runs'][:2]
        if len(pair) != 2 or pair[0]['pair_id'] != pair[1]['pair_id']:
            return False
        pair_dir = directory / pair[0]['pair_id']
        if [path for path in directory.iterdir() if path.is_dir()] != [pair_dir] or (pair_dir / 'complete.json').exists():
            return False
        interruptions = sorted(directory.glob('interruption-*.json'))
        error = json.loads(interruptions[-1].read_text())['error']
        if not error.startswith("Command '['docker', 'stats', '--no-stream'") or not error.endswith('returned non-zero exit status 1.'):
            return False
        expected = {run['run_id']: run for run in pair}
        runs = list(pair_dir.rglob('run.json'))
        return bool(runs) and all(json.loads(path.read_text()) == expected.get(path.parent.name) for path in runs)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return False


def install(project, campaign, payload):
    LOCK.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (LOCK.parent / 'session.sock').exists():
            raise ValueError('Há uma sessão de ensaios aberta; encerre-a antes da atualização')
        current = fingerprint(project)
        expected = payload['source_hashes']
        metadata_path = campaign / 'campaign.json'
        original_metadata = metadata_path.read_bytes()
        metadata = json.loads(original_metadata)
        if metadata['source_hashes'] != current:
            raise ValueError('A versão instalada diverge da campanha registrada; atualização recusada')
        if current == expected:
            print('A execução em sequência já está instalada. Nenhum ensaio iniciado.')
            return
        changed = {name for name in current.keys() | expected.keys() if current.get(name) != expected.get(name)}
        if not changed.issubset(FILES) or set(payload['files']) != set(FILES):
            raise ValueError('Há mudanças fora da execução em sequência; atualização recusada')
        failed_start = (campaign / 'blocks').exists() and failed_before_restore(campaign)
        generator_failure = changed == {'load/recursos_bloco.py'} and failed_during_generator_transition(campaign)
        if (campaign / 'blocks').exists() and not failed_start and not generator_failure:
            raise ValueError('Já há blocos registrados; preserve a campanha e revise a atualização antes de continuar')
        for name in FILES:
            if hashlib.sha256(payload['files'][name].encode()).hexdigest() != expected.get(name):
                raise ValueError('Conteúdo da atualização divergente: ' + name)
        audit = campaign / ('preparation-sequencia-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        audit.mkdir()
        (audit / 'campaign.json').write_bytes(original_metadata)
        if failed_start or generator_failure:
            shutil.copytree(campaign / 'blocks', audit / 'blocks')
        originals = {name: (project / name).read_bytes() if (project / name).exists() else None for name in FILES}
        for name, content in originals.items():
            if content is not None:
                backup = audit / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(content)
        try:
            for name in FILES:
                target = project / name
                temporary = target.with_suffix('.sequence.tmp')
                temporary.write_text(payload['files'][name])
                temporary.chmod(0o644)
                temporary.replace(target)
            if fingerprint(project) != expected:
                raise ValueError('Conferência da instalação divergente')
            metadata['source_hashes'] = expected
            metadata['sequence_preparation'] = audit.name
            if failed_start:
                metadata['pre_execution_repair'] = {'reason': MISSING_BACKUP, 'backup': audit.name, 'measurements_started': False}
            if generator_failure:
                metadata['generator_collection_repair'] = {'reason': 'Contêiner k6 encerrado entre identificação e coleta de recursos',
                    'backup': audit.name, 'previous_attempts_valid_for_campaign': False, 'resume': 'Repetir os dois modos do primeiro par; manter as tentativas anteriores.'}
            temporary = metadata_path.with_suffix('.sequence.tmp')
            temporary.write_text(json.dumps(metadata, indent=2) + '\n')
            temporary.replace(metadata_path)
        except BaseException:
            for name, content in originals.items():
                target = project / name
                if content is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(content)
            metadata_path.write_bytes(original_metadata)
            raise
        print('Sequência instalada, com cópia da versão anterior em ' + str(audit))
        print('Plano, base e parâmetros preservados. Nenhum ensaio iniciado.')


def prepare():
    config = json.loads((PROJECT / 'load/campanha.json').read_text())
    payload = {'source_hashes': fingerprint(PROJECT), 'files': {name: (PROJECT / name).read_text() for name in FILES}}
    destination = config['ssh_user'] + '@' + config['load_host']
    with tempfile.TemporaryDirectory(prefix='tcc-sequencia-') as temporary:
        temporary = Path(temporary)
        bundle = temporary / 'bundle.json'
        bundle.write_text(json.dumps(payload))
        control = str(temporary / 'ssh')
        options = ['-S', control, '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3']
        subprocess.run(['ssh', '-fN', '-M', *options, '-o', 'ControlPersist=60', destination], check=True)
        remote = None
        try:
            remote = subprocess.check_output(['ssh', *options, destination, 'mktemp -d /tmp/tcc-sequencia-XXXXXXXX'], text=True).strip()
            subprocess.run(['scp', '-o', 'ControlPath=' + control, str(bundle), str(Path(__file__).resolve()), destination + ':' + remote + '/'], check=True)
            command = ['sudo', 'python3', remote + '/preparar_sequencia.py', '--instalar', remote + '/bundle.json',
                       '--projeto', config['remote_project'], '--campanha', config['campaign']]
            subprocess.run(['ssh', '-tt', *options, destination, shlex.join(command)], check=True)
        finally:
            if remote:
                cleanup = "from pathlib import Path; p=Path(" + repr(remote) + "); (p/'bundle.json').unlink(missing_ok=True); (p/'preparar_sequencia.py').unlink(missing_ok=True); p.rmdir()"
                subprocess.run(['ssh', *options, destination, 'python3 -c ' + shlex.quote(cleanup)], check=False)
            subprocess.run(['ssh', '-S', control, '-O', 'exit', destination], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description='Instala a execução em sequência antes da campanha, sem iniciar carga ou alterar serviços.')
    parser.add_argument('--instalar', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--projeto', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--campanha', type=Path, help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if arguments.instalar:
        if os.geteuid() != 0 or arguments.projeto is None or arguments.campanha is None:
            parser.error('A instalação remota exige sudo, projeto e campanha')
        install(arguments.projeto, arguments.campanha, json.loads(arguments.instalar.read_text()))
    else:
        prepare()


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print('Preparação interrompida: ' + str(error), file=sys.stderr)
        sys.exit(1)
