import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

LOAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOAD))
import executar

specification = importlib.util.spec_from_file_location('dispatch_invalid', LOAD / 'hooks.vm/dispatch.py')
hooks = importlib.util.module_from_spec(specification)
specification.loader.exec_module(hooks)


class InvalidMonitoringCleanupTests(unittest.TestCase):
    def test_cleanup_stops_and_preserves_every_raw_file_without_valid_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'monitoring').mkdir()
            summary = directory / 'measurement-summary.json'
            summary.write_text('{invalid JSON')
            environment = {'RUN_DIR': str(directory), 'RUN_ID': 'case', 'MEASUREMENT_SUMMARY': str(summary),
                           'MONITOR_MODE': 'cleanup'}
            raw = b'{"sample":1}\n'
            response = {'monitoring_stopped': True, 'jsonl': base64.b64encode(raw).decode()}
            with patch.dict(os.environ, environment), patch.object(hooks, 'remote', return_value=response) as remote, patch.object(hooks.subprocess, 'run') as summarize:
                receipt = hooks.monitor_stop()
            self.assertTrue(receipt['monitoring_stopped'])
            self.assertFalse(receipt['summaries_generated'])
            self.assertEqual(set(hooks.SERVICES), set(receipt['raw_files_preserved']))
            summarize.assert_not_called()
            self.assertEqual(set(hooks.SERVICES), {call.args[0] for call in remote.call_args_list})
            for call in remote.call_args_list:
                self.assertEqual('monitor-stop', call.args[1])
                self.assertEqual(0, call.args[-1])
            for service in hooks.SERVICES:
                self.assertEqual(raw, (directory / f'monitoring/{service}.jsonl').read_bytes())
                self.assertFalse((directory / f'monitoring/{service}-summary.json').exists())

    def test_other_raw_files_survive_a_service_stop_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'monitoring').mkdir()
            environment = {'RUN_DIR': str(directory), 'RUN_ID': 'case', 'MONITOR_MODE': 'cleanup',
                           'MEASUREMENT_SUMMARY': str(directory / 'missing.json')}
            raw = b'{"sample":1}\n'
            def stop(service, *arguments):
                if service == 'redis':
                    raise RuntimeError('SSH desconectado')
                return {'monitoring_stopped': True, 'jsonl': base64.b64encode(raw).decode()}
            with patch.dict(os.environ, environment), patch.object(hooks, 'remote', side_effect=stop):
                with self.assertRaisesRegex(RuntimeError, 'redis: SSH desconectado'):
                    hooks.monitor_stop()
            for service in ('app', 'postgres'):
                self.assertEqual(raw, (directory / f'monitoring/{service}.jsonl').read_bytes())

    def test_cleanup_requires_explicit_confirmation_from_every_collector(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'monitoring').mkdir()
            environment = {'RUN_DIR': str(directory), 'RUN_ID': 'case', 'MONITOR_MODE': 'cleanup',
                           'MEASUREMENT_SUMMARY': str(directory / 'missing.json')}
            response = {'monitoring_stopped': False, 'jsonl': base64.b64encode(b'{}\n').decode()}
            with patch.dict(os.environ, environment), patch.object(hooks, 'remote', return_value=response):
                with self.assertRaisesRegex(RuntimeError, 'Parada dos coletores não confirmada'):
                    hooks.monitor_stop()


class AbortedTrialTests(unittest.TestCase):
    def fixture(self, directory):
        run = {'run_id': '90-10-vu500-r4-on', 'profile': '90-10', 'virtual_users': 500,
               'seed': '4f3d22ebb78520f6', 'cache_mode': 'on'}
        arguments = SimpleNamespace(saida=directory, hooks=LOAD / 'hooks.vm', backup=directory / 'backup.dump',
                                    base_url='http://10.20.20.10:8080')
        return {'manifest_sha256': 'manifest-hash'}, run, arguments

    def test_abort_keeps_original_invalid_cause_and_only_requests_raw_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            plan, run, arguments = self.fixture(directory)
            reason = ValueError('PATCH falhou: estado persistido incerto')
            with patch.object(executar, 'run_hook') as hook, patch.object(executar, 'run_k6', side_effect=[None, reason]):
                with self.assertRaises(ValueError) as raised:
                    executar.execute_run(plan, run, arguments, directory / 'manifest.json', 'backup-hash')
            self.assertIs(reason, raised.exception)
            case = directory / run['run_id']
            self.assertEqual({'valid': False, 'error': str(reason)}, json.loads((case / 'invalid.json').read_text()))
            self.assertFalse((case / 'complete.json').exists())
            stop_calls = [call for call in hook.call_args_list if call.args[1] == 'monitor-stop']
            self.assertEqual(1, len(stop_calls))
            self.assertEqual('cleanup', stop_calls[0].args[2]['MONITOR_MODE'])

    def test_cleanup_failure_does_not_mask_primary_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            plan, run, arguments = self.fixture(directory)
            reason = ValueError('k6 interrompido: PATCH falhou')
            def hook(path, action, environment, expected):
                if action == 'monitor-stop':
                    raise RuntimeError('redis: SSH desconectado')
            with patch.object(executar, 'run_hook', side_effect=hook), patch.object(executar, 'run_k6', side_effect=[None, reason]):
                with self.assertRaises(ValueError) as raised:
                    executar.execute_run(plan, run, arguments, directory / 'manifest.json', 'backup-hash')
            self.assertIs(reason, raised.exception)
            case = directory / run['run_id']
            self.assertEqual(str(reason), json.loads((case / 'invalid.json').read_text())['error'])
            self.assertEqual('redis: SSH desconectado', json.loads((case / 'monitor-cleanup-error.json').read_text())['error'])
            self.assertFalse((case / 'complete.json').exists())

    def test_k6_failure_reports_abort_cause_and_preserves_full_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            environment = {'BASE_URL': 'http://10.20.20.10:8080', 'RUN_ID': 'case', 'PROFILE': '90-10',
                           'VUS': '500', 'SEED': 'seed', 'CACHE_MODE': 'on'}
            def docker(command, **options):
                if command[:2] == ['docker', 'run']:
                    options['stdout'].write('time="2026-10-24" level=error msg="PATCH falhou: estado persistido incerto"\n')
                    (directory / 'measurement-summary.json').write_text(json.dumps({'valid': False, 'write_errors': 1}))
                    raise subprocess.CalledProcessError(108, command)
                return subprocess.CompletedProcess(command, 0)
            with patch.object(executar.subprocess, 'run', side_effect=docker):
                with self.assertRaises(ValueError) as raised:
                    executar.run_k6(LOAD, directory, directory / 'manifest.json', 'measurement', environment)
            message = str(raised.exception)
            self.assertIn('código 108', message)
            self.assertIn('PATCH falhou', message)
            self.assertIn(str(directory / 'k6-measurement.log'), message)
            self.assertNotIn('--mount', message)
            diagnostic = json.loads((directory / 'k6-measurement-error.json').read_text())
            self.assertEqual(108, diagnostic['exit_code'])
            self.assertEqual({'valid': False, 'write_errors': 1}, diagnostic['summary_data'])
            self.assertIn('PATCH falhou', diagnostic['log_excerpt'][-1])

    def test_container_cleanup_timeout_does_not_replace_k6_abort(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            environment = {'BASE_URL': 'http://10.20.20.10:8080', 'RUN_ID': 'case', 'PROFILE': '90-10',
                           'VUS': '500', 'SEED': 'seed', 'CACHE_MODE': 'on'}
            def docker(command, **options):
                if command[:2] == ['docker', 'run']:
                    options['stdout'].write('level=error msg="PATCH falhou"\n')
                    raise subprocess.CalledProcessError(108, command)
                raise subprocess.TimeoutExpired(command, 20)
            with patch.object(executar.subprocess, 'run', side_effect=docker):
                with self.assertRaisesRegex(ValueError, 'código 108'):
                    executar.run_k6(LOAD, directory, directory / 'manifest.json', 'measurement', environment)
            self.assertTrue((directory / 'k6-measurement-cleanup-error.json').is_file())


if __name__ == '__main__':
    unittest.main()
