#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'load'))
from intervalo_blocos import parse_blocks

CONFIG = json.loads((PROJECT / 'load/campanha.json').read_text())
GIB = 1024 ** 3
SESSION = CONFIG['terminal_session']


def snapshot(token):
    filesystem = os.statvfs(PROJECT)
    image = Path('/var/lib/libvirt/images/tcc/tcc-postgres.qcow2')
    allocated = image.stat().st_blocks * 512
    return {'token': token, 'timestamp_unix': time.time(), 'free_bytes': filesystem.f_bavail * filesystem.f_frsize,
            'image_allocated_bytes': allocated, 'required_start_bytes': max(0, 35 * GIB - allocated) + 13 * GIB,
            'budget': 'LV PostgreSQL de 32 GiB, boot de 2 GiB, 1 GiB de margem da imagem, reserva de 12 GiB e resultados de 1 GiB'}


def collect_package(destination, control, local, remote, name):
    temporary = local / (name + '.part')
    checksum = local / (name + '.sha256.part')
    try:
        for filename, target in ((name, temporary), (name + '.sha256', checksum)):
            subprocess.run(['scp', '-o', 'ControlPath=' + control, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                            '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
                            destination + ':' + remote + '/exports/' + filename, str(target)], check=True, timeout=180)
        expected = checksum.read_text().split()[0]
        digest = hashlib.sha256()
        with temporary.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError('Pacote transferido com hash divergente: ' + name)
        temporary.replace(local / name)
        checksum.replace(local / (name + '.sha256'))
    finally:
        temporary.unlink(missing_ok=True)
        checksum.unlink(missing_ok=True)
    print('Pacote conferido e salvo no notebook: ' + str(local / name), flush=True)


def collect_block(destination, control, local, number):
    collect_package(destination, control, local, CONFIG['campaign'], f'bloco-{number:02d}.zip')


def collect_results(destination, control, local, numbers, require_all):
    failed = False
    for number in numbers:
        remote = CONFIG['campaign'] + f'/exports/bloco-{number:02d}.zip'
        available = subprocess.run(['ssh', '-S', control, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                                    destination, 'test -f ' + shlex.quote(remote)], timeout=30)
        if available.returncode:
            print(f'Bloco {number:02d}: pacote ainda não disponível para cópia.', flush=True)
            failed = failed or require_all or available.returncode != 1
            continue
        try:
            collect_block(destination, control, local, number)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            print(f'Falha na cópia do bloco {number:02d}: {error}. Use --recolher {number}.', flush=True)
            failed = True
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description='Executa um bloco ou sequência no TCC e copia os pacotes para o notebook ao terminar.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--bloco', type=int, choices=range(1, 21))
    group.add_argument('--blocos', type=parse_blocks, metavar='INICIO-FIM')
    group.add_argument('--verificar', action='store_true')
    group.add_argument('--consolidar', action='store_true')
    group.add_argument('--recolher', type=int, choices=range(1, 21))
    group.add_argument('--piloto', action='store_true', help='Executa somente o piloto de capacidade, fora dos resultados da campanha.')
    group.add_argument('--piloto-leitura', action='store_true', help='Confere a capacidade em 100/0 com cache e 500 VUs, fora da campanha.')
    arguments = parser.parse_args()
    numbers = arguments.blocos or ([arguments.bloco or arguments.recolher] if arguments.bloco or arguments.recolher else [])
    if not os.environ.get('TMUX'):
        if not shutil.which('tmux'):
            parser.error('tmux não encontrado no notebook')
        raise SystemExit(subprocess.call(['tmux', 'new-session', '-A', '-s', SESSION, shlex.join([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])]))
    if not os.environ.get('TCC_SLEEP_GUARD'):
        environment = dict(os.environ, TCC_SLEEP_GUARD='1')
        raise SystemExit(subprocess.call(['systemd-inhibit', '--what=sleep', '--mode=block', '--why=Campanha do TCC em execução', sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env=environment))
    local = PROJECT / 'results' / Path(CONFIG['campaign']).name
    if arguments.piloto_leitura:
        local = local / 'piloto-leitura-v3'
    local.mkdir(parents=True, exist_ok=True)
    destination = CONFIG['ssh_user'] + '@' + CONFIG['load_host']
    token = secrets.token_hex(16)
    stop = threading.Event()
    heartbeat = None
    sender = None
    exit_code = 0
    with tempfile.TemporaryDirectory(prefix='tcc-ssh-') as temporary:
        control = str(Path(temporary) / 'ssh')
        options = ['-S', control, '-o', 'StrictHostKeyChecking=yes', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3']
        subprocess.run(['ssh', '-fN', '-M', *options, '-o', 'ControlPersist=60', destination], check=True)
        try:
            if not arguments.consolidar and not arguments.recolher:
                receiver = 'python3 ' + CONFIG['remote_project'] + '/load/receber_host.py'
                sender = subprocess.Popen(['ssh', *options, destination, receiver], stdin=subprocess.PIPE, text=True)
                def transmit():
                    while not stop.is_set():
                        try:
                            sender.stdin.write(json.dumps(snapshot(token)) + '\n')
                            sender.stdin.flush()
                        except (OSError, ValueError):
                            return
                        stop.wait(5)
                heartbeat = threading.Thread(target=transmit, daemon=True)
                heartbeat.start()
                time.sleep(2)
            action = 'executar' if arguments.bloco or arguments.blocos else ('consolidar' if arguments.consolidar else 'verificar')
            command = ['sudo', 'python3', CONFIG['remote_project'] + '/load/blocos.py', action, '--campanha', CONFIG['campaign']]
            if arguments.piloto or arguments.piloto_leitura:
                command = ['sudo', 'python3', CONFIG['remote_project'] + '/scripts/piloto_capacidade.py', '--campanha', CONFIG['campaign']]
                if arguments.piloto_leitura:
                    command.append('--somente-leitura')
                    print('Piloto somente leitura: autentique no início. Reserve 12 minutos; um caso será executado fora da campanha.', flush=True)
                else:
                    print('Piloto de capacidade: autentique no início. Reserve 25 minutos; os dois modos serão executados fora da campanha.', flush=True)
            if arguments.bloco:
                command += ['--bloco', str(arguments.bloco)]
            elif arguments.blocos:
                command += ['--blocos', f'{numbers[0]}-{numbers[-1]}']
                print(f'Sequência {numbers[0]:02d} a {numbers[-1]:02d}: autentique no início. Os pacotes serão copiados ao encerrar a sequência.', flush=True)
            if action != 'consolidar':
                command += ['--host-token', token]
            if not arguments.recolher:
                try:
                    exit_code = subprocess.call(['ssh', '-tt', *options, destination, shlex.join(command)])
                except KeyboardInterrupt:
                    exit_code = 130
            if numbers:
                copy_code = collect_results(destination, control, local, numbers, require_all=exit_code == 0)
                exit_code = exit_code or copy_code
            elif arguments.piloto or arguments.piloto_leitura:
                remote = str(Path(CONFIG['campaign']).parent / ('piloto-leitura-v3' if arguments.piloto_leitura else 'piloto-capacidade-v3'))
                try:
                    collect_package(destination, control, local, remote, 'piloto-capacidade.zip')
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    print('Falha ao copiar o piloto; os dados permanecem na geradora: ' + str(error), flush=True)
                    exit_code = exit_code or 1
            elif arguments.consolidar and exit_code == 0:
                subprocess.run(['scp', '-o', 'ControlPath=' + control, destination + ':' + CONFIG['campaign'] + '/exports/consolidacao.zip', str(local)], check=True)
            if arguments.verificar:
                subprocess.run(['scp', '-o', 'ControlPath=' + control, destination + ':' + CONFIG['campaign'] + '/conferencia.json', str(local)], check=False)
        finally:
            stop.set()
            if heartbeat:
                heartbeat.join(timeout=10)
            if sender:
                sender.stdin.close()
                try:
                    sender.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    sender.terminate()
            subprocess.run(['ssh', '-S', control, '-O', 'exit', destination], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('Operação encerrada. Para acompanhar novamente: tmux attach -t ' + SESSION)
    if exit_code:
        print('Consulte os pacotes disponíveis. ' + ('Um novo piloto repetirá seus casos, preservando esta tentativa.' if arguments.piloto or arguments.piloto_leitura else 'Reexecute o mesmo bloco ou intervalo para retomar os pares pendentes.'))
    input('Pressione Enter para fechar este terminal de acompanhamento.')
    raise SystemExit(exit_code)


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print('Operação interrompida: ' + str(error))
        input('Pressione Enter para fechar este terminal de acompanhamento.')
        raise SystemExit(1)
