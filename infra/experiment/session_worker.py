#!/usr/bin/python3
import base64
import importlib.util
import json
import signal
import sys
import termios
from pathlib import Path

specification = importlib.util.spec_from_file_location('remote_agent', '/opt/tcc-experiment/remote_agent.py')
module = importlib.util.module_from_spec(specification)
specification.loader.exec_module(module)
agent = module.Agent(json.loads(Path('/etc/tcc-experiment.json').read_text()))
attributes = termios.tcgetattr(sys.stdin.fileno())
attributes[3] &= ~termios.ECHO
termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, attributes)
active = set()


def finish(signum, frame):
    raise SystemExit(0)


signal.signal(signal.SIGHUP, finish)
signal.signal(signal.SIGTERM, finish)
print('TCC_SESSION_READY', flush=True)
try:
    for line in sys.stdin:
        request = json.loads(line)
        action = request['action']
        values = request.get('values', [])
        if action == 'exit':
            break
        operations = {'status': agent.status, 'stop': agent.stop, 'mode': agent.mode, 'restore': agent.restore,
                      'verify': agent.verify, 'clear': agent.clear, 'monitor-start': agent.monitor_start,
                      'monitor-stop': agent.monitor_stop}
        try:
            if action not in operations:
                raise ValueError('Operação fora do experimento')
            result = operations[action](*values)
            if action == 'monitor-start':
                active.add(values[0])
            if action == 'monitor-stop':
                active.discard(values[0])
            response = {'ok': True, 'value': result}
        except Exception as error:
            response = {'ok': False, 'error': type(error).__name__ + ': ' + str(error)}
        encoded = base64.b64encode(json.dumps(response).encode()).decode()
        print('TCC_RESULT:' + encoded, flush=True)
finally:
    for run_id in active:
        try:
            agent.stop_collector(agent.run_directory(run_id))
        except (OSError, ValueError):
            pass
