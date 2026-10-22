#!/usr/bin/env python3
import argparse
import base64
import getpass
import json
import os
import pty
import select
import shlex
import signal
import socket
import socketserver
import struct
import threading
import time
from pathlib import Path


ROOT = Path('/run/tcc-experiment')
SOCKET = ROOT / 'session.sock'
KNOWN_HOSTS = '/home/rhyan/tcc-experimento/ssh/known_hosts'


class Session:
    def __init__(self, service, password):
        self.service = service
        self.lock = threading.Lock()
        host = '10.20.20.10' if service == 'app' else {'postgres': '10.10.10.20', 'redis': '10.10.10.30'}[service]
        command = ['ssh', '-tt', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={KNOWN_HOSTS}', '-o', 'NumberOfPasswordPrompts=1']
        if service == 'app':
            command += ['-M', '-S', str(ROOT / 'jump')]
        else:
            proxy = ['ssh', '-S', str(ROOT / 'jump'), '-W', '%h:%p', 'rhyan@10.20.20.10']
            command += ['-o', 'ProxyCommand=' + shlex.join(proxy)]
        command += ['rhyan@' + host, 'sudo -k /usr/bin/python3 /opt/tcc-experiment/session_worker.py']
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execvp(command[0], command)
        self.buffer = b''
        deadline = time.monotonic() + 60
        answers = 0
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.fd], [], [], 1)
            if not ready:
                continue
            received = os.read(self.fd, 65536)
            if not received:
                raise ConnectionError('Sessão encerrada durante autenticação: ' + service)
            self.buffer += received
            if b'TCC_SESSION_READY' in self.buffer:
                self.buffer = self.buffer.split(b'TCC_SESSION_READY', 1)[1]
                return
            if b'password' in self.buffer.lower() and self.buffer.rstrip().endswith(b':'):
                answers += 1
                if answers > 2:
                    raise RuntimeError('Autenticação recusada: ' + service)
                os.write(self.fd, password.encode() + b'\n')
                self.buffer = b''
        raise RuntimeError('Autenticação não terminou: ' + service)

    def request(self, action, values):
        with self.lock:
            os.write(self.fd, json.dumps({'action': action, 'values': values}).encode() + b'\n')
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline:
                while b'\n' in self.buffer:
                    line, self.buffer = self.buffer.split(b'\n', 1)
                    line = line.strip()
                    if line.startswith(b'TCC_RESULT:'):
                        return json.loads(base64.b64decode(line[len(b'TCC_RESULT:'):]))
                ready, _, _ = select.select([self.fd], [], [], 1)
                if ready:
                    received = os.read(self.fd, 65536)
                    if not received:
                        raise ConnectionError('Sessão encerrada: ' + self.service)
                    self.buffer += received
            raise RuntimeError('Tempo esgotado: ' + self.service)

    def close(self):
        try:
            os.write(self.fd, b'{"action":"exit"}\n')
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if os.waitpid(self.pid, os.WNOHANG)[0]:
                    return
                time.sleep(0.1)
            os.kill(self.pid, signal.SIGTERM)
        except (OSError, ChildProcessError):
            pass
        finally:
            os.close(self.fd)


def main():
    parser = argparse.ArgumentParser(description='Autentica sessões temporárias SSH/sudo; não guarda senhas ou cria privilégios permanentes.')
    parser.add_argument('--lifetime-seconds', type=int, default=3600)
    arguments = parser.parse_args()
    if arguments.lifetime_seconds <= 0:
        raise ValueError('A duração da sessão deve ser positiva')
    if os.getuid() != 0:
        raise ValueError('Iniciar com sudo para proteger o socket das sessões')
    ROOT.mkdir(mode=0o700, exist_ok=True)
    if SOCKET.exists():
        raise ValueError('Já existe uma sessão de ensaios')
    sessions = {}
    server = None
    try:
        for service in ('app', 'postgres', 'redis'):
            password = getpass.getpass('Senha SSH/sudo de tcc-' + service + ': ')
            sessions[service] = Session(service, password)
            del password
            print('Sessão autenticada: tcc-' + service, flush=True)

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                credentials = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
                if struct.unpack('3i', credentials)[1] != 0:
                    return
                try:
                    request = json.loads(self.rfile.readline(4096))
                    response = sessions[request['service']].request(request['action'], request.get('values', []))
                except BaseException as error:
                    response = {'ok': False, 'error': str(error)}
                self.wfile.write(json.dumps(response).encode() + b'\n')

        server = socketserver.ThreadingUnixStreamServer(str(SOCKET), Handler)
        SOCKET.chmod(0o600)
        deadline = time.monotonic() + arguments.lifetime_seconds
        server.timeout = 1
        print('TCC_MANUAL_READY', flush=True)
        while time.monotonic() < deadline:
            server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.server_close()
        for service in ('postgres', 'redis', 'app'):
            if service in sessions:
                sessions[service].close()
        SOCKET.unlink(missing_ok=True)
        (ROOT / 'jump').unlink(missing_ok=True)


if __name__ == '__main__':
    main()
