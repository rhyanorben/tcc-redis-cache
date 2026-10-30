import importlib.util
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'scripts'))
import executar_bloco
import piloto_capacidade


class ManualPilotTests(unittest.TestCase):
    def fixture(self, directory):
        campaign = directory / 'results/campaign-v2'
        campaign.mkdir(parents=True)
        runs = [{'profile': '100-0', 'virtual_users': 25, 'repetition': 1, 'sequence': index} for index in range(1, 201)]
        for index, mode in ((10, 'on'), (11, 'off')):
            runs[index] = {'profile': '90-10', 'virtual_users': 500, 'repetition': 4, 'sequence': index + 1,
                           'run_id': '90-10-vu500-r4-' + mode, 'pair_id': '90-10-vu500-r4', 'seed': 'original', 'cache_mode': mode}
        (campaign / 'plan.json').write_text(json.dumps({'runs': runs}))
        (campaign / 'manifesto.json').write_text('{"reference":"unchanged"}')
        (campaign / 'campaign.json').write_text('{"source_hashes":{"load/workload.js":"original"}}')
        return campaign, runs[10:12]

    def test_selects_exact_original_pair_without_reordering_or_changing_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            campaign, pair = self.fixture(Path(temporary))
            plan = piloto_capacidade.blocos.read(campaign / 'plan.json')
            before = json.dumps(plan)
            self.assertEqual(pair, piloto_capacidade.selected_pair(plan))
            self.assertEqual(before, json.dumps(plan))
            plan['runs'][10]['sequence'] = 13
            with self.assertRaisesRegex(ValueError, 'posições 11 e 12'):
                piloto_capacidade.selected_pair(plan)

    def test_manual_pilot_authenticates_once_preserves_both_runs_and_is_outside_campaign(self):
        with tempfile.TemporaryDirectory() as temporary:
            campaign, pair = self.fixture(Path(temporary))
            plan_before = (campaign / 'plan.json').read_bytes()
            broker = Mock()
            def trial(plan, run, arguments, manifest, backup_hash):
                directory = arguments.saida / run['run_id']
                directory.mkdir()
                (directory / 'partial-data.json').write_text('{"sample":1}')
            with patch.dict(piloto_capacidade.CONFIG, {'campaign': str(campaign)}), patch.object(piloto_capacidade.blocos, 'session_start', return_value=broker) as authenticate, patch.object(piloto_capacidade.blocos, 'session_stop') as close, patch.object(piloto_capacidade.blocos, 'preflight', return_value={'ready': True}), patch.object(piloto_capacidade, 'Resources') as resources, patch.object(piloto_capacidade.executar, 'execute_run', side_effect=trial) as execute, patch.object(piloto_capacidade.blocos, 'summarize_generator') as summarize:
                piloto_capacidade.execute_pilot(campaign, 'token')
            authenticate.assert_called_once_with(lifetime_seconds=7200)
            close.assert_called_once_with(broker)
            resources.return_value.close.assert_called_once()
            self.assertEqual(pair, [call.args[1] for call in execute.call_args_list])
            summarize.assert_called_once()
            self.assertEqual(plan_before, (campaign / 'plan.json').read_bytes())
            self.assertFalse((campaign / 'blocks').exists())
            root = campaign.parent / 'piloto-capacidade-v2'
            state = piloto_capacidade.blocos.read(next(root.glob('tentativa-*/pilot.json')))
            self.assertEqual('complete', state['status'])
            self.assertFalse(state['eligible_for_campaign'])
            self.assertTrue(state['excluded_from_campaign'])
            self.assertEqual(piloto_capacidade.executar.file_hash(Path(piloto_capacidade.__file__)), state['script_sha256'])
            archive = root / 'exports/piloto-capacidade.zip'
            with zipfile.ZipFile(archive) as package:
                self.assertIsNone(package.testzip())
                self.assertIn('SHA256.json', package.namelist())
                self.assertEqual(2, len([name for name in package.namelist() if name.endswith('partial-data.json')]))
            self.assertEqual(piloto_capacidade.executar.file_hash(archive), archive.with_suffix('.zip.sha256').read_text().split()[0])

    def test_failed_run_is_packaged_broker_closed_and_retry_repeats_both_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            campaign, pair = self.fixture(Path(temporary))
            error = ValueError('aborto do k6')
            with patch.dict(piloto_capacidade.CONFIG, {'campaign': str(campaign)}), patch.object(piloto_capacidade.blocos, 'session_start', return_value=Mock()), patch.object(piloto_capacidade.blocos, 'session_stop') as close, patch.object(piloto_capacidade.blocos, 'preflight', return_value={}), patch.object(piloto_capacidade, 'Resources'), patch.object(piloto_capacidade.executar, 'execute_run', side_effect=[None, error]) as execute, patch.object(piloto_capacidade.blocos, 'summarize_generator') as summarize:
                with self.assertRaises(ValueError) as raised:
                    piloto_capacidade.execute_pilot(campaign, 'token')
                self.assertIs(error, raised.exception)
                self.assertEqual(2, execute.call_count)
                close.assert_called_once()
                summarize.assert_not_called()
                execute.reset_mock(side_effect=True)
                piloto_capacidade.execute_pilot(campaign, 'token')
                self.assertEqual(pair, [call.args[1] for call in execute.call_args_list])
            root = campaign.parent / 'piloto-capacidade-v2'
            states = [piloto_capacidade.blocos.read(path) for path in sorted(root.glob('tentativa-*/pilot.json'))]
            self.assertEqual(['interrupted', 'complete'], [state['status'] for state in states])
            self.assertTrue(all(state['eligible_for_campaign'] is False for state in states))
            with zipfile.ZipFile(root / 'exports/piloto-capacidade.zip') as package:
                self.assertEqual(2, len([name for name in package.namelist() if name.endswith('/pilot.json')]))

    def test_preflight_failure_never_runs_load_and_still_packages_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            campaign, pair = self.fixture(Path(temporary))
            with patch.dict(piloto_capacidade.CONFIG, {'campaign': str(campaign)}), patch.object(piloto_capacidade.blocos, 'session_start', return_value=Mock()), patch.object(piloto_capacidade.blocos, 'session_stop') as close, patch.object(piloto_capacidade.blocos, 'preflight', side_effect=ValueError('imagem divergente')), patch.object(piloto_capacidade.executar, 'execute_run') as execute:
                with self.assertRaisesRegex(ValueError, 'imagem divergente'):
                    piloto_capacidade.execute_pilot(campaign, 'token')
            execute.assert_not_called()
            close.assert_called_once()
            self.assertTrue((campaign.parent / 'piloto-capacidade-v2/exports/piloto-capacidade.zip').exists())


class PilotLauncherTests(unittest.TestCase):
    def test_manual_switch_routes_to_pilot_and_copies_package_even_after_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(executar_bloco, 'PROJECT', Path(temporary)), patch.dict(os.environ, {'TMUX': 'test', 'TCC_SLEEP_GUARD': '1'}), patch.object(sys, 'argv', ['executar_bloco.py', '--piloto']), patch.object(executar_bloco.subprocess, 'run'), patch.object(executar_bloco.subprocess, 'Popen', return_value=Mock()), patch.object(executar_bloco.subprocess, 'call', return_value=108) as call, patch.object(executar_bloco.threading, 'Thread', return_value=Mock()), patch.object(executar_bloco.time, 'sleep'), patch.object(executar_bloco, 'collect_package') as collect, patch.object(executar_bloco, 'collect_results') as blocks, patch('builtins.input'):
                with self.assertRaises(SystemExit) as result:
                    executar_bloco.main()
            self.assertEqual(108, result.exception.code)
            command = call.call_args.args[0][-1]
            self.assertIn('/scripts/piloto_capacidade.py', command)
            self.assertIn('--host-token', command)
            self.assertNotIn('/load/blocos.py', command)
            self.assertEqual('piloto-capacidade.zip', collect.call_args.args[-1])
            self.assertTrue(collect.call_args.args[-2].endswith('/results/piloto-capacidade-v2'))
            blocks.assert_not_called()


if __name__ == '__main__':
    unittest.main()
