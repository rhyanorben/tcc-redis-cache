import argparse
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import blocos
from intervalo_blocos import parse_blocks
from test_load import manifest_rows
from criar_manifesto import build_manifest
from planejar import build_plan
from test_outcomes import summary_fixture


def fixture(root):
    manifest = root / 'manifesto.json'
    manifest.write_text(json.dumps(build_manifest(manifest_rows(), 'exp-001')))
    plan = build_plan(manifest, 20261032)
    blocos.write(root / 'plan.json', plan)
    blocos.write(root / 'campaign.json', {})
    blocos.write(root / 'blocos.json', [])
    return plan


def fake_run(plan, run, arguments, manifest, backup):
    directory = arguments.saida / run['run_id']
    directory.mkdir()
    blocos.write(directory / 'run.json', run)
    blocos.write(directory / 'complete.json', {'complete': True})
    window = {'measurement_start_unix_ms': 1000, 'measurement_end_unix_ms': 301000, 'measurement_completed_unix_ms': 302000}
    blocos.write(directory / 'measurement-summary.json', {**summary_fixture(3), 'valid_for_campaign': True, **window})
    for service in ('app', 'postgres', 'redis'):
        blocos.write(directory / f'monitoring/{service}-summary.json', {'scope': 'measurement_resources_with_bracketed_counters', 'service': service, 'measurement_window': window})


class BlocksTest(unittest.TestCase):
    def test_blocks_cover_original_order_exactly_and_keep_pairs_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = fixture(Path(temporary))
            blocks = blocos.split_blocks(plan)
            self.assertEqual(20, len(blocks))
            self.assertEqual(plan['runs'], [run for block in blocks for run in block])
            self.assertTrue(all(len(block) == 10 for block in blocks))
            plan['runs'][1], plan['runs'][2] = plan['runs'][2], plan['runs'][1]
            with self.assertRaises(ValueError):
                blocos.split_blocks(plan)

    def test_interruption_repeats_both_modes_and_preserves_completed_pairs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = fixture(root)
            calls = []
            def fail_second_pair(plan, run, arguments, manifest, backup):
                calls.append(run['run_id'])
                if len(calls) == 4:
                    raise RuntimeError('queda simulada')
                fake_run(plan, run, arguments, manifest, backup)
            with patch.object(blocos, 'session_start', return_value=Mock()), patch.object(blocos, 'preflight', return_value={}), patch.object(blocos, 'host_state'), patch.object(blocos, 'Resources'), patch.object(blocos, 'summarize_generator'), patch.object(blocos.executar, 'execute_run', side_effect=fail_second_pair):
                with self.assertRaises(RuntimeError):
                    blocos.execute_block(root, 1, 'token')
            first_pair = plan['runs'][0]['pair_id']
            complete = root / 'blocks/bloco-01' / first_pair / 'complete.json'
            first_receipt = complete.read_bytes()
            calls.clear()
            def retry(plan, run, arguments, manifest, backup):
                calls.append(run['run_id'])
                fake_run(plan, run, arguments, manifest, backup)
            with patch.object(blocos, 'session_start', return_value=Mock()), patch.object(blocos, 'preflight', return_value={}), patch.object(blocos, 'host_state'), patch.object(blocos, 'Resources'), patch.object(blocos, 'summarize_generator'), patch.object(blocos.executar, 'execute_run', side_effect=retry):
                blocos.execute_block(root, 1, 'token')
            self.assertEqual(8, len(calls))
            self.assertEqual(plan['runs'][2]['run_id'], calls[0])
            self.assertEqual(plan['runs'][3]['run_id'], calls[1])
            self.assertEqual(first_receipt, complete.read_bytes())
            with zipfile.ZipFile(root / 'exports/bloco-01.zip') as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn('SHA256.json', archive.namelist())
            pair_dir = complete.parent
            receipt = json.loads(complete.read_text())
            (pair_dir / receipt['attempt'] / plan['runs'][0]['run_id'] / 'run.json').write_text('{}')
            self.assertFalse(blocos.validate_pair(pair_dir, plan['runs'][:2]))

    def test_cannot_start_block_two_before_block_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            with patch.object(blocos, 'session_start') as session:
                with self.assertRaises(ValueError):
                    blocos.execute_block(root, 2, 'token')
                session.assert_not_called()

    def test_block_passes_backup_to_real_trial_executor_with_external_actions_intercepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = fixture(root)
            window = {'measurement_start_unix_ms': 1000, 'measurement_end_unix_ms': 301000, 'measurement_completed_unix_ms': 302000}
            def k6(project, directory, manifest, phase, environment):
                if phase == 'measurement':
                    summary = {**summary_fixture(3), 'valid_for_campaign': True, **window}
                    blocos.write(directory / 'measurement-summary.json', summary)
                    return summary
            def hook(path, action, environment, expected):
                if action == 'monitor-stop':
                    directory = Path(environment['RUN_DIR'])
                    for service in ('app', 'postgres', 'redis'):
                        blocos.write(directory / f'monitoring/{service}-summary.json', {'scope': 'measurement_resources_with_bracketed_counters', 'service': service, 'measurement_window': window})
            with patch.object(blocos, 'session_start', return_value=Mock()), patch.object(blocos, 'preflight', return_value={}), patch.object(blocos, 'Resources'), patch.object(blocos, 'summarize_generator'), patch.object(blocos.executar, 'run_k6', side_effect=k6) as load, patch.object(blocos.executar, 'run_hook', side_effect=hook) as hooks:
                blocos.execute_block(root, 1, 'token')
            restores = [call for call in hooks.call_args_list if call.args[1] == 'restore']
            self.assertEqual(10, len(restores))
            self.assertEqual(20, load.call_count)
            for call in restores:
                self.assertEqual(str(Path(blocos.CONFIG['backup']).resolve()), call.args[2]['BACKUP_PATH'])
                self.assertEqual(blocos.CONFIG['backup_sha256'], call.args[2]['BACKUP_SHA256'])
            for index in range(0, 10, 2):
                pair = plan['runs'][index:index + 2]
                self.assertTrue(blocos.validate_pair(root / 'blocks/bloco-01' / pair[0]['pair_id'], pair))


class SequenceTest(unittest.TestCase):
    def test_interval_rejects_reversed_out_of_range_or_disconnected_blocks(self):
        self.assertEqual([2, 3, 4, 5], parse_blocks('2-5'))
        for value in ('5-2', '0-4', '1-21', '1,3', '1-3; reboot', '-1-4', '2', '02-05'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                parse_blocks(value)

    def test_sequence_authenticates_once_and_closes_only_after_last_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            broker = Mock()
            broker.poll.return_value = None
            visited = []
            def execute(root, number, token, shared_session):
                self.assertIs(broker, shared_session)
                broker.send_signal.assert_not_called()
                visited.append(number)
            with patch.object(blocos, 'session_start', return_value=broker) as authenticate, patch.object(blocos, 'execute_block', side_effect=execute):
                blocos.execute_sequence(root, [1, 2, 3], 'token')
            self.assertEqual([1, 2, 3], visited)
            authenticate.assert_called_once_with(lifetime_seconds=28800)
            broker.send_signal.assert_called_once()
            receipt = blocos.read(next((root / 'sequences').glob('*.json')))
            self.assertEqual('complete', receipt['status'])
            self.assertEqual([1, 2, 3], receipt['completed_blocks'])

    def test_sequence_stops_at_first_failure_and_preserves_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            broker = Mock()
            broker.poll.return_value = None
            visited = []
            def execute(root, number, token, shared_session):
                visited.append(number)
                if number == 2:
                    raise RuntimeError('coleta interrompida')
            with patch.object(blocos, 'session_start', return_value=broker) as authenticate, patch.object(blocos, 'execute_block', side_effect=execute):
                with self.assertRaisesRegex(RuntimeError, 'coleta interrompida'):
                    blocos.execute_sequence(root, [1, 2, 3], 'token')
            self.assertEqual([1, 2], visited)
            authenticate.assert_called_once()
            broker.send_signal.assert_called_once()
            receipt = blocos.read(next((root / 'sequences').glob('*.json')))
            self.assertEqual('interrupted', receipt['status'])
            self.assertEqual([1], receipt['completed_blocks'])
            self.assertEqual(2, receipt['current_block'])

    def test_sequence_cannot_skip_previous_blocks_or_request_disconnected_numbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            for numbers in ([2, 3], [1, 3], [20, 21], []):
                with self.subTest(numbers=numbers), patch.object(blocos, 'session_start') as authenticate:
                    with self.assertRaises(ValueError):
                        blocos.execute_sequence(root, numbers, 'token')
                    authenticate.assert_not_called()

    def test_expired_shared_session_never_asks_for_password_again(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root)
            broker = Mock()
            broker.poll.return_value = 0
            with patch.object(blocos, 'session_start') as authenticate, patch.object(blocos.executar, 'execute_run') as execute:
                with self.assertRaisesRegex(RuntimeError, 'sem nova autenticação'):
                    blocos.execute_block(root, 1, 'token', shared_session=broker)
                authenticate.assert_not_called()
                execute.assert_not_called()
            self.assertTrue((root / 'exports/bloco-01.zip').is_file())

    def test_real_block_flow_resumes_sequence_after_partial_second_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = fixture(root)
            broker = Mock()
            broker.poll.return_value = None
            calls = []
            def fail_during_second_block(plan, run, arguments, manifest, backup):
                calls.append(run['run_id'])
                if len(calls) == 14:
                    raise RuntimeError('falha simulada no bloco 2')
                fake_run(plan, run, arguments, manifest, backup)
            with patch.object(blocos, 'session_start', return_value=broker) as authenticate, patch.object(blocos, 'preflight', return_value={}), patch.object(blocos, 'Resources'), patch.object(blocos, 'summarize_generator'), patch.object(blocos.executar, 'execute_run', side_effect=fail_during_second_block):
                with self.assertRaisesRegex(RuntimeError, 'bloco 2'):
                    blocos.execute_sequence(root, [1, 2, 3], 'token')
                authenticate.assert_called_once()
                broker.send_signal.assert_called_once()
            self.assertTrue((root / 'exports/bloco-01.zip').exists())
            self.assertTrue((root / 'exports/bloco-02.zip').exists())
            self.assertFalse((root / 'blocks/bloco-03').exists())
            first_receipt = (root / 'blocks/bloco-01/complete.json').read_bytes()
            retried = []
            def retry(plan, run, arguments, manifest, backup):
                retried.append(run['run_id'])
                fake_run(plan, run, arguments, manifest, backup)
            with patch.object(blocos, 'session_start', return_value=broker) as authenticate, patch.object(blocos, 'preflight', return_value={}), patch.object(blocos, 'Resources'), patch.object(blocos, 'summarize_generator'), patch.object(blocos.executar, 'execute_run', side_effect=retry):
                blocos.execute_sequence(root, [1, 2, 3], 'token')
                authenticate.assert_called_once()
            self.assertEqual(18, len(retried))
            self.assertEqual(plan['runs'][12]['run_id'], retried[0])
            self.assertEqual(plan['runs'][13]['run_id'], retried[1])
            self.assertEqual(first_receipt, (root / 'blocks/bloco-01/complete.json').read_bytes())
            for number in (1, 2, 3):
                with zipfile.ZipFile(root / f'exports/bloco-{number:02d}.zip') as archive:
                    self.assertIsNone(archive.testzip())

class HostGuardTest(unittest.TestCase):
    def test_stale_or_low_disk_heartbeat_is_rejected(self):
        import recursos_bloco
        from unittest.mock import mock_open
        import time
        for sample in ({'token': 't', 'timestamp_unix': time.time() - 100, 'free_bytes': 20 * 1024**3},
                       {'token': 't', 'timestamp_unix': time.time(), 'free_bytes': 10 * 1024**3}):
            with patch.object(Path, 'read_text', return_value=json.dumps(sample)):
                with self.assertRaises(ValueError):
                    recursos_bloco.host_state('t')


if __name__ == '__main__':
    unittest.main()
