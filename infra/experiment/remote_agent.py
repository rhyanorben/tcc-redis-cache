#!/usr/bin/python3
import argparse
import base64
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path


DATABASE = 'tcc_experimento'
IMAGE = 'sha256:55f2b25ac4de19ceb22aa867ce78b17e3266a707d2ad676d42c534610831c35b'
DATABASE_MARKER = 'TCC_EXPERIMENT_20261022'


def execute(arguments, input_data=None, timeout=1800):
    result = subprocess.run(arguments, input=input_data, capture_output=True, timeout=timeout)
    if result.returncode:
        sys.stderr.buffer.write(result.stderr)
        raise RuntimeError(f'{arguments[0]} terminou com código {result.returncode}')
    return result.stdout.decode()


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def valid_run_id(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
        raise ValueError('Identificador de execução inválido')
    return value


class Agent:
    def __init__(self, config):
        self.config = config
        self.role = config['service']
        if socket.gethostname() != 'tcc-' + self.role:
            raise ValueError('VM diferente da configuração')
        if config['database'] != DATABASE:
            raise ValueError('Banco fora do destino experimental')
        self.compose = Path(config['compose'])
        self.root = Path(config['root'])
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def compose_command(self, extra_files=()):
        return ['docker', 'compose', '--project-directory', str(self.compose.parent),
                '-f', str(self.compose), *[part for name in extra_files for part in ('-f', str(self.compose.parent / name))]]

    def sql(self, query, database=DATABASE):
        if self.role != 'postgres' or database not in (DATABASE, 'postgres'):
            raise ValueError('Consulta fora do PostgreSQL experimental')
        return execute(self.compose_command() + ['exec', '-T', 'postgres', 'psql', '-XAtq',
                       '-v', 'ON_ERROR_STOP=1', '-U', 'tcc_admin', '-d', database, '-c', query]).strip()

    def database_guard(self):
        marker = self.sql("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname='tcc_experimento'", 'postgres')
        if marker != DATABASE_MARKER:
            raise ValueError('Banco sem identificação experimental')

    def status(self):
        container = execute(self.compose_command() + ['ps', '-q', self.role]).strip()
        if not container:
            return {'service': self.role, 'running': False}
        inspected = json.loads(execute(['docker', 'inspect', container]))[0]
        result = {'service': self.role, 'running': inspected['State']['Running'], 'image': inspected['Image']}
        if self.role == 'app':
            environment = dict(entry.split('=', 1) for entry in inspected['Config']['Env'])
            result.update(cache_mode='on' if environment.get('CACHE_ENABLED') == 'true' else 'off', database_url=environment.get('DB_URL'))
        return result

    def stop(self):
        if self.role != 'app':
            raise ValueError('Somente a aplicação pode ser parada')
        execute(self.compose_command() + ['stop', '--timeout', '30', 'app'])
        return {'stopped': True}

    def mode(self, mode):
        if self.role != 'app' or mode not in ('on', 'off'):
            raise ValueError('Modo inválido')
        files = ['compose.ethernet.yaml', 'compose.experiment.yaml']
        if mode == 'on':
            files.append('compose.cache.yaml')
        image = execute(['docker', 'image', 'inspect', 'tcc-pedidos:0.1.0', '--format', '{{.Id}}']).strip()
        if image != IMAGE:
            raise ValueError('A imagem da aplicação foi alterada')
        execute(self.compose_command(files) + ['up', '-d', '--no-build', 'app'])
        for attempt in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8081/actuator/health', timeout=2) as response:
                    if json.load(response)['status'] == 'UP':
                        break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('API não ficou pronta')
        status = self.status()
        if status['image'] != IMAGE or status['cache_mode'] != mode or '/tcc_experimento?' not in status['database_url']:
            raise ValueError('Configuração efetiva da API divergente')
        return status

    def restore(self, expected_hash):
        self.database_guard()
        backup = Path(self.config['backup'])
        if expected_hash != self.config['backup_sha256'] or digest(backup) != expected_hash:
            raise ValueError('Backup diferente da referência validada')
        connections = self.sql("SELECT count(*) FROM pg_stat_activity WHERE datname='tcc_experimento' AND usename='tcc_app'")
        if connections != '0':
            raise ValueError('Aplicação ainda conectada; restauração recusada')
        if os.statvfs('/').f_bavail * os.statvfs('/').f_frsize < 5 * 1024**3:
            raise ValueError('Espaço insuficiente para restauração segura')
        with backup.open('rb') as source:
            result = subprocess.run(self.compose_command() + ['exec', '-T', 'postgres', 'pg_restore', '-U', 'tcc_admin',
                                    '-d', DATABASE, '--clean', '--if-exists', '--exit-on-error', '--single-transaction'],
                                    stdin=source, capture_output=True, timeout=1800)
        if result.returncode:
            sys.stderr.buffer.write(result.stderr)
            raise RuntimeError('Restauração falhou')
        self.sql('ANALYZE tcc.empresa; ANALYZE tcc.cliente; ANALYZE tcc.pedido; ANALYZE tcc.item_pedido;')
        return {'backup_sha256': expected_hash, 'counts': self.counts()}

    def counts(self):
        self.database_guard()
        result = json.loads(self.sql("SELECT json_build_object('empresa',(SELECT count(*) FROM tcc.empresa),'cliente',(SELECT count(*) FROM tcc.cliente),'pedido',(SELECT count(*) FROM tcc.pedido),'item_pedido',(SELECT count(*) FROM tcc.item_pedido),'bytes',pg_database_size(current_database()))"))
        expected = {'empresa': 100, 'cliente': 500000, 'pedido': 2000000, 'item_pedido': 6000000}
        if any(result[key] != value for key, value in expected.items()):
            raise ValueError('Contagens diferentes da base completa')
        return result

    def verify(self):
        counts = self.counts()
        query = Path(self.config['export_sql']).read_bytes()
        csv = execute(self.compose_command() + ['exec', '-T', 'postgres', 'psql', '-Xq', '-v', 'ON_ERROR_STOP=1',
                      '-U', 'tcc_admin', '-d', DATABASE, '-v', 'lote=base-v1'], input_data=query)
        return {'counts': counts, 'csv': base64.b64encode(csv.encode()).decode()}

    def redis_command(self, command):
        if self.role != 'redis':
            raise ValueError('Somente Redis aceita este comando')
        shell = 'REDISCLI_AUTH="$(cat /run/secrets/redis_password)" redis-cli --no-auth-warning --raw ' + command
        return execute(self.compose_command() + ['exec', '-T', 'redis', 'sh', '-c', shell]).strip()

    def clear(self):
        keys = self.redis_command('--scan').splitlines()
        if any(not key.startswith('tcc:') for key in keys):
            raise ValueError('Redis contém dados fora do experimento')
        self.redis_command('FLUSHDB SYNC')
        if self.redis_command('DBSIZE') != '0':
            raise ValueError('Redis não ficou vazio')
        return {'cache_empty': True, 'previous_keys': len(keys)}

    def run_directory(self, run_id):
        return self.root / valid_run_id(run_id)

    def monitor_start(self, run_id):
        directory = self.run_directory(run_id)
        directory.mkdir(mode=0o700, exist_ok=False)
        output = directory / 'samples.jsonl'
        command = [sys.executable, self.config['collector'], '--service', self.role, '--compose', str(self.compose),
                   '--database', DATABASE, '--output', str(output), '--duration', '3600', '--interval', '5']
        with (directory / 'collector.log').open('wb') as log:
            process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        state = {'pid': process.pid, 'start_ticks': Path(f'/proc/{process.pid}/stat').read_text().split()[21]}
        (directory / 'process.json').write_text(json.dumps(state))
        for attempt in range(30):
            try:
                first = json.loads(output.read_text().splitlines()[0])
                if first.get('error'):
                    raise RuntimeError('Primeira amostra inválida')
                return {'monitoring_ready': True, 'service': self.role}
            except (FileNotFoundError, IndexError, json.JSONDecodeError):
                if process.poll() is not None:
                    raise RuntimeError('Coletor encerrou antes da primeira amostra')
                time.sleep(1)
        self.stop_collector(directory)
        raise RuntimeError('Coletor não produziu amostra inicial')

    def stop_collector(self, directory):
        state = json.loads((directory / 'process.json').read_text())
        process = Path(f'/proc/{state["pid"]}')
        if process.exists() and (process / 'stat').read_text().split()[21] == state['start_ticks']:
            if self.config['collector'].encode() not in (process / 'cmdline').read_bytes():
                raise RuntimeError('PID não pertence ao coletor')
            os.kill(state['pid'], signal.SIGTERM)

    def monitor_stop(self, run_id, completed_ms):
        directory = self.run_directory(run_id)
        output = directory / 'samples.jsonl'
        try:
            if completed_ms:
                for attempt in range(30):
                    lines = output.read_text().splitlines()
                    try:
                        last = json.loads(lines[-1])
                        started_ms = datetime.fromisoformat(last['timestamp']).timestamp() * 1000
                        if started_ms > completed_ms + 2000:
                            break
                    except (IndexError, json.JSONDecodeError):
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError('Amostra final não cobre a conclusão da carga')
        finally:
            self.stop_collector(directory)
        lines = [json.loads(line) for line in output.read_text().splitlines()]
        if any('error' in sample for sample in lines):
            raise RuntimeError('Coleta contém erro')
        return {'monitoring_stopped': True, 'service': self.role, 'jsonl': base64.b64encode(output.read_bytes()).decode()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('status', 'stop', 'mode', 'restore', 'verify', 'clear', 'monitor-start', 'monitor-stop'))
    parser.add_argument('value', nargs='?')
    parser.add_argument('completed_ms', nargs='?', type=int, default=0)
    arguments = parser.parse_args()
    agent = Agent(json.loads(Path('/etc/tcc-experiment.json').read_text()))
    actions = {'status': lambda: agent.status(), 'stop': lambda: agent.stop(), 'mode': lambda: agent.mode(arguments.value),
               'restore': lambda: agent.restore(arguments.value), 'verify': lambda: agent.verify(), 'clear': lambda: agent.clear(),
               'monitor-start': lambda: agent.monitor_start(arguments.value),
               'monitor-stop': lambda: agent.monitor_stop(arguments.value, arguments.completed_ms)}
    print(json.dumps(actions[arguments.action](), ensure_ascii=False))


if __name__ == '__main__':
    main()
