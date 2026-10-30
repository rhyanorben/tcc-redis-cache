import argparse
import fcntl
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import executar
from intervalo_blocos import parse_blocks
from outcomes import validate_outcomes
from recursos_bloco import GIB, Resources, host_state

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((PROJECT / 'load/campanha.json').read_text())
SERVICES = ('app', 'postgres', 'redis')
sys.path.insert(0, str(PROJECT / 'load/hooks.vm'))
from dispatch import remote


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def fingerprint():
    paths = [path for folder in ('load', 'monitoring', 'infra/experiment') for path in (PROJECT / folder).rglob('*')
             if path.suffix in ('.py', '.js', '.json') and '__pycache__' not in path.parts and 'tests' not in path.parts]
    return {str(path.relative_to(PROJECT)): executar.file_hash(path) for path in sorted(paths)}


def split_blocks(plan):
    runs = plan['runs']
    if len(runs) != 200:
        raise ValueError('A campanha exige 200 execuções')
    for index in range(0, 200, 2):
        left, right = runs[index:index + 2]
        if left['pair_id'] != right['pair_id'] or left['seed'] != right['seed'] or {left['cache_mode'], right['cache_mode']} != {'on', 'off'}:
            raise ValueError('Os pares precisam estar completos e consecutivos')
    return [runs[index:index + 10] for index in range(0, 200, 10)]


def prepare(root, plan_path, manifest):
    plan = read(plan_path)
    executar.validate_plan(plan, manifest)
    if CONFIG['protocol_version'] != plan['protocol_version']:
        raise ValueError('A configuração não corresponde ao protocolo do plano.')
    blocks = split_blocks(plan)
    root.mkdir(parents=True, exist_ok=False)
    shutil.copy2(manifest, root / 'manifesto.json')
    plan['manifest_path'] = str((root / 'manifesto.json').resolve())
    write(root / 'plan.json', plan)
    write(root / 'blocos.json', [{'block': index, 'runs': [run['run_id'] for run in block], 'minimum_minutes': 70, 'estimated_minutes': [80, 105]} for index, block in enumerate(blocks, 1)])
    write(root / 'campaign.json', {'created_at': datetime.now(timezone.utc).isoformat(), 'protocol_version': CONFIG['protocol_version'],
          'app_image': CONFIG['app_image'], 'supersedes': CONFIG['supersedes'], 'backup_sha256': CONFIG['backup_sha256'],
          'navigation': plan['navigation'], 'source_hashes': fingerprint(), 'pilot_included': False})
    print('20 blocos preparados; nenhum ensaio iniciado.')


def package(root, number):
    directory = root / 'blocks' / f'bloco-{number:02d}'
    exports = root / 'exports'
    exports.mkdir(exist_ok=True)
    destination = exports / f'bloco-{number:02d}.zip'
    files = [root / name for name in ('plan.json', 'manifesto.json', 'campaign.json', 'blocos.json')]
    if (root / 'runtime.json').exists():
        files.append(root / 'runtime.json')
    files += sorted(path for path in directory.rglob('*') if path.is_file())
    inventory = {str(path.relative_to(root)): executar.file_hash(path) for path in files}
    temporary = destination.with_suffix('.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, str(path.relative_to(root)))
        archive.writestr('SHA256.json', json.dumps(inventory, indent=2))
    temporary.replace(destination)
    destination.with_suffix('.zip.sha256').write_text(executar.file_hash(destination) + '  ' + destination.name + '\n')
    print('Resultados salvos: ' + str(destination), flush=True)


def validate_pair(directory, pair):
    try:
        receipt = read(directory / 'complete.json')
        attempt = directory / receipt['attempt']
        if attempt.parent.resolve() != directory.resolve() or not attempt.is_dir():
            return False
        for name, expected in receipt.get('sha256', {}).items():
            if executar.file_hash(attempt / name) != expected:
                return False
        if not receipt.get('sha256'):
            return False
        for run in pair:
            case = attempt / run['run_id']
            if (case / 'invalid.json').exists() or not read(case / 'complete.json')['complete'] or read(case / 'run.json') != run:
                return False
            summary = read(case / 'measurement-summary.json')
            if not summary.get('valid_for_campaign') or summary['nominal_measurement_seconds'] != 300:
                return False
            if summary.get('protocol_version') != CONFIG['protocol_version']:
                return False
            validate_outcomes(summary)
            executar.validate_monitoring(case, summary)
        return True
    except (OSError, ValueError, KeyError):
        return False


def preflight(root, token):
    plan = read(root / 'plan.json')
    executar.validate_plan(plan, root / 'manifesto.json')
    metadata = read(root / 'campaign.json')
    if metadata.get('protocol_version') != CONFIG['protocol_version'] or metadata.get('app_image') != CONFIG['app_image']:
        raise ValueError('A campanha pertence a outro protocolo ou imagem da API; não misturar resultados')
    if metadata.get('navigation') != plan['navigation']:
        raise ValueError('A campanha pertence a outra configuração de navegação')
    if metadata['source_hashes'] != fingerprint():
        raise ValueError('Os scripts mudaram após preparar a campanha; não misturar versões')
    if executar.file_hash(Path(CONFIG['backup'])) != CONFIG['backup_sha256']:
        raise ValueError('Backup da geradora divergente')
    notebook = host_state(token)
    if notebook['free_bytes'] < notebook['required_start_bytes']:
        raise ValueError('Espaço no notebook abaixo do orçamento de início registrado')
    if subprocess.check_output(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'], text=True).strip() != 'yes':
        raise ValueError('Relógio da geradora não sincronizado')
    subprocess.run(['docker', 'image', 'inspect', plan['k6_image']], check=True, stdout=subprocess.DEVNULL)
    with ThreadPoolExecutor(max_workers=3) as pool:
        statuses = dict(zip(SERVICES, pool.map(lambda service: remote(service, 'preflight'), SERVICES)))
    if any(not status['status']['running'] or not status['ntp_synchronized'] for status in statuses.values()):
        raise ValueError('Serviço indisponível ou relógio não sincronizado')
    if statuses['postgres']['free_bytes'] < 5 * GIB or statuses['postgres']['filesystem_bytes'] > 33 * GIB:
        raise ValueError('Disco PostgreSQL fora do orçamento validado de 32 GiB')
    if statuses['app'].get('health') != 'UP' or '/tcc_experimento?' not in statuses['app']['status']['database_url']:
        raise ValueError('API fora do banco experimental ou indisponível')
    if statuses['app']['status']['image'] != CONFIG['app_image']:
        raise ValueError('Imagem da API divergente')
    runtime = {service: {'cpus': status['cpus'], 'memory_total_kib_rounded': round(status['memory_total_kib'] / 65536) * 65536, 'image': status['status']['image'], 'parameters': status['parameters']} for service, status in statuses.items()}
    runtime['load'] = {'cpus': os.cpu_count(), 'memory_total_kib_rounded': round(int(Path('/proc/meminfo').read_text().splitlines()[0].split()[1]) / 65536) * 65536}
    reference = root / 'runtime.json'
    if reference.exists() and read(reference) != runtime:
        raise ValueError('Recursos, imagens, índices ou parâmetros mudaram durante a campanha')
    if not reference.exists():
        write(reference, runtime)
    import socket
    with socket.create_connection(('10.20.20.10', 8080), timeout=5):
        pass
    return {'timestamp': datetime.now(timezone.utc).isoformat(), 'notebook': notebook, 'services': statuses, 'load_cpus': os.cpu_count(), 'load_free_bytes': shutil.disk_usage('/').free}


def session_start(lifetime_seconds=14400):
    if Path('/run/tcc-experiment/session.sock').exists():
        raise ValueError('Já existe sessão manual; encerre-a antes de executar o bloco')
    process = subprocess.Popen([sys.executable, str(PROJECT / 'infra/experiment/manual_session.py'), '--lifetime-seconds', str(lifetime_seconds)])
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('A autenticação manual não foi concluída')
        if Path('/run/tcc-experiment/session.sock').exists():
            return process
        time.sleep(0.5)
    process.send_signal(signal.SIGINT)
    process.wait(timeout=40)
    raise RuntimeError('Tempo para autenticação esgotado')


def session_stop(process):
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=45)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=15)


def summarize_generator(attempt, pair):
    samples = [json.loads(line) for line in (attempt / 'gerador.jsonl').read_text().splitlines()]
    for run in pair:
        directory = attempt / run['run_id']
        summary = read(directory / 'measurement-summary.json')
        window = [sample for sample in samples if summary['measurement_start_unix_ms'] <= datetime.fromisoformat(sample['timestamp']).timestamp() * 1000 <= summary['measurement_end_unix_ms']]
        stats = [container for sample in window for container in sample['generator']]
        if len(stats) < 20:
            raise ValueError('Acompanhamento da geradora não cobre a medição')
        cpu = [float(container['CPUPerc'].rstrip('%')) for container in stats]
        write(directory / 'gerador-summary.json', {'samples': len(stats), 'cpu_percent_one_core_mean': statistics.mean(cpu),
              'cpu_percent_one_core_max': max(cpu), 'container_memory_percent_max': max(float(container['MemPerc'].rstrip('%')) for container in stats),
              'notebook_free_bytes_min': min(sample['notebook']['free_bytes'] for sample in window),
              'possible_generator_cpu_bottleneck': statistics.mean(cpu) >= 320})


def require_previous_blocks(root, number):
    blocks = split_blocks(read(root / 'plan.json'))
    for previous in range(1, number):
        previous_runs = blocks[previous - 1]
        previous_dir = root / 'blocks' / f'bloco-{previous:02d}'
        if any(not validate_pair(previous_dir / previous_runs[index]['pair_id'], previous_runs[index:index + 2]) for index in range(0, 10, 2)):
            raise ValueError('Conclua os blocos anteriores antes deste bloco')


def execute_block(root, number, token, shared_session=None):
    block = split_blocks(read(root / 'plan.json'))[number - 1]
    require_previous_blocks(root, number)
    directory = root / 'blocks' / f'bloco-{number:02d}'
    directory.mkdir(parents=True, exist_ok=True)
    complete = lambda: all(validate_pair(directory / block[index]['pair_id'], block[index:index + 2]) for index in range(0, 10, 2))
    if complete():
        package(root, number)
        print('Este bloco já está completo; nenhum ensaio repetido.')
        return
    broker = None
    try:
        if shared_session is None:
            broker = session_start()
        elif shared_session.poll() is not None:
            raise RuntimeError('A sessão manual terminou; sequência interrompida sem nova autenticação')
        write(directory / 'preflight.json', preflight(root, token))
        arguments = SimpleNamespace(saida=None, hooks=PROJECT / 'load/hooks.vm', base_url=CONFIG['base_url'], backup=Path(CONFIG['backup']))
        for index in range(0, 10, 2):
            pair = block[index:index + 2]
            pair_dir = directory / pair[0]['pair_id']
            if validate_pair(pair_dir, pair):
                print('Par já concluído: ' + pair[0]['pair_id'], flush=True)
                continue
            write(directory / ('preflight-par-' + str(index // 2 + 1) + '.json'), preflight(root, token))
            pair_dir.mkdir(exist_ok=True)
            attempt = pair_dir / ('tentativa-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            attempt.mkdir()
            arguments.saida = attempt
            resources = Resources(attempt / 'gerador.jsonl', token)
            resources.start()
            try:
                for run in pair:
                    print(f"Bloco {number:02d}/20 — execução {run['sequence']}/200: {run['run_id']}", flush=True)
                    executar.execute_run(read(root / 'plan.json'), run, arguments, root / 'manifesto.json', CONFIG['backup_sha256'])
            finally:
                resources.close()
            summarize_generator(attempt, pair)
            hashes = {str(path.relative_to(attempt)): executar.file_hash(path) for path in attempt.rglob('*') if path.is_file()}
            write(pair_dir / 'complete.json', {'complete': True, 'attempt': attempt.name, 'sha256': hashes})
            package(root, number)
        write(directory / 'complete.json', {'complete': True, 'block': number, 'pairs': 5, 'runs': 10})
    except BaseException as error:
        write(directory / ('interruption-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'), {'error': str(error), 'timestamp': datetime.now(timezone.utc).isoformat(), 'resume': 'Executar novamente o mesmo bloco; pares completos serão preservados.'})
        raise
    finally:
        if broker:
            session_stop(broker)
        package(root, number)


def execute_sequence(root, numbers, token):
    if not numbers or numbers != list(range(numbers[0], numbers[-1] + 1)) or not 1 <= numbers[0] <= numbers[-1] <= 20:
        raise ValueError('A sequência deve ser um intervalo crescente entre 1 e 20')
    require_previous_blocks(root, numbers[0])
    started = datetime.now(timezone.utc)
    receipt = root / 'sequences' / (started.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    state = {'blocks': numbers, 'completed_blocks': [], 'status': 'authenticating', 'started_at': started.isoformat()}
    write(receipt, state)
    broker = None
    try:
        lifetime = max(14400, (len(numbers) + 1) * 7200)
        broker = session_start(lifetime_seconds=lifetime)
        for number in numbers:
            state.update(status='running', current_block=number)
            write(receipt, state)
            execute_block(root, number, token, shared_session=broker)
            state['completed_blocks'].append(number)
            write(receipt, state)
        state['status'] = 'complete'
    except BaseException as error:
        state.update(status='interrupted', error=str(error))
        raise
    finally:
        state['ended_at'] = datetime.now(timezone.utc).isoformat()
        try:
            write(receipt, state)
        finally:
            if broker:
                session_stop(broker)
    print('Sequência concluída. Nenhum bloco adicional será iniciado.', flush=True)


def consolidate(root):
    plan = read(root / 'plan.json')
    selected = root / 'selected'
    selected.mkdir(exist_ok=True)
    for number, block in enumerate(split_blocks(plan), 1):
        for index in range(0, 10, 2):
            pair = block[index:index + 2]
            directory = root / 'blocks' / f'bloco-{number:02d}' / pair[0]['pair_id']
            if not validate_pair(directory, pair):
                raise ValueError(f'Bloco {number:02d} incompleto; consolidação não iniciada')
            attempt = directory / read(directory / 'complete.json')['attempt']
            for run in pair:
                link = selected / run['run_id']
                if link.is_symlink():
                    link.unlink()
                link.symlink_to((attempt / run['run_id']).resolve(), target_is_directory=True)
    output = root / ('consolidacao-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    subprocess.run([sys.executable, str(PROJECT / 'load/resumir.py'), '--resultados', str(selected), '--saida', str(output)], check=True)
    destination = root / 'exports/consolidacao.zip'
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in output.iterdir():
            archive.write(path, path.name)
    print('Consolidação salva: ' + str(destination))


def interrupted(signum, frame):
    raise KeyboardInterrupt('Execução interrompida; os resultados parciais serão preservados')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('preparar', 'executar', 'verificar', 'consolidar'))
    parser.add_argument('--campanha', type=Path, default=Path(CONFIG['campaign']))
    parser.add_argument('--plano', type=Path)
    parser.add_argument('--manifesto', type=Path)
    blocks = parser.add_mutually_exclusive_group()
    blocks.add_argument('--bloco', type=int, choices=range(1, 21))
    blocks.add_argument('--blocos', type=parse_blocks, metavar='INICIO-FIM')
    parser.add_argument('--host-token')
    arguments = parser.parse_args()
    if arguments.action == 'preparar':
        prepare(arguments.campanha, arguments.plano, arguments.manifesto)
        return
    if os.geteuid() != 0:
        parser.error('A operação na geradora deve ser iniciada com sudo')
    Path('/run/tcc-experiment').mkdir(mode=0o700, exist_ok=True)
    with Path('/run/tcc-experiment/campaign.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGHUP, interrupted)
        if arguments.action == 'executar':
            if arguments.bloco is None and arguments.blocos is None or not arguments.host_token:
                parser.error('Informe bloco ou intervalo e acompanhamento do notebook')
            if arguments.blocos:
                execute_sequence(arguments.campanha, arguments.blocos, arguments.host_token)
            else:
                execute_block(arguments.campanha, arguments.bloco, arguments.host_token)
        elif arguments.action == 'consolidar':
            consolidate(arguments.campanha)
        else:
            broker = session_start()
            try:
                result = preflight(arguments.campanha, arguments.host_token)
                write(arguments.campanha / 'conferencia.json', result)
                print('Conferência aprovada: serviços, base, backup, rede, relógios e orçamento de disco.')
            finally:
                session_stop(broker)


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print('Bloco interrompido: ' + str(error), file=sys.stderr)
        sys.exit(1)
