import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

GIB = 1024 ** 3


def host_state(token):
    sample = json.loads(Path('/home/rhyan/.cache/tcc-experimento/host-atual.json').read_text())
    if sample['token'] != token or abs(time.time() - sample['timestamp_unix']) > 30:
        raise ValueError('Acompanhamento do notebook ausente ou desatualizado')
    if sample['free_bytes'] < 12 * GIB:
        raise ValueError('Notebook abaixo da reserva de 12 GiB; bloco interrompido')
    return sample


def running_generators():
    result = subprocess.run(['docker', 'ps', '--no-trunc', '--filter', 'name=tcc-k6-', '--format', '{{.ID}}'],
                            capture_output=True, text=True, check=True, timeout=10)
    return result.stdout.split()


def generator_stats():
    containers = running_generators()
    ended = []
    for attempt in range(2):
        if not containers:
            return [], ended
        result = subprocess.run(['docker', 'stats', '--no-stream', '--format', '{{json .}}', *containers],
                                capture_output=True, text=True, check=False, timeout=15)
        if result.returncode == 0:
            return [json.loads(line) for line in result.stdout.splitlines()], ended
        remaining = set(running_generators())
        disappeared = [container for container in containers if container not in remaining]
        if not disappeared:
            result.check_returncode()
        ended.extend(disappeared)
        containers = [container for container in containers if container in remaining]
    if containers:
        result.check_returncode()
    return [], ended


class Resources:
    def __init__(self, path, token):
        self.path = path
        self.token = token
        self.stop_event = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self.collect, daemon=True)

    def start(self):
        self.thread.start()

    def collect(self):
        with self.path.open('x') as output:
            while not self.stop_event.is_set():
                try:
                    host = host_state(self.token)
                    if os.statvfs('/').f_bavail * os.statvfs('/').f_frsize < 2 * GIB:
                        raise ValueError('Geradora abaixo da reserva de 2 GiB')
                    stats, ended = generator_stats()
                    sample = {'timestamp': datetime.now(timezone.utc).isoformat(), 'loadavg': os.getloadavg(), 'generator': stats,
                              'generator_containers_ended': ended, 'notebook': host}
                    output.write(json.dumps(sample) + '\n')
                    output.flush()
                except Exception as error:
                    self.error = str(error)
                    os.kill(os.getpid(), 15)
                    return
                self.stop_event.wait(5)

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=20)
        if self.error:
            raise RuntimeError(self.error)
