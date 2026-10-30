import fcntl
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import executar_bloco
import preparar_sequencia


class CollectionTest(unittest.TestCase):
    def test_corrupt_copy_preserves_previous_valid_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary)
            archive = local / 'bloco-01.zip'
            archive.write_bytes(b'original')
            def transfer(command, **kwargs):
                target = Path(command[-1])
                target.write_bytes(b'corrupted' if target.name.endswith('.zip.part') else b'wrong  bloco-01.zip\n')
            with patch.object(executar_bloco.subprocess, 'run', side_effect=transfer):
                with self.assertRaisesRegex(ValueError, 'hash divergente'):
                    executar_bloco.collect_block('rhyan@load', 'control', local, 1)
            self.assertEqual(b'original', archive.read_bytes())
            self.assertFalse(list(local.glob('*.part')))

    def test_interrupted_sequence_recovers_available_blocks_and_continues_after_copy_failure(self):
        with patch.object(executar_bloco.subprocess, 'run', side_effect=[Mock(returncode=0), Mock(returncode=0), Mock(returncode=1)]), patch.object(executar_bloco, 'collect_block', side_effect=[ValueError('erro'), None]) as collect:
            code = executar_bloco.collect_results('rhyan@load', 'control', Path('/tmp'), [1, 2, 3], require_all=False)
        self.assertEqual(1, code)
        self.assertEqual([1, 2], [call.args[-1] for call in collect.call_args_list])


class PreparationTest(unittest.TestCase):
    def fixture(self, root):
        project = root / 'runner'
        campaign = project / 'results/campaign'
        for name in ('load/blocos.py', 'load/workload.js', 'monitoring/coletar.py', 'infra/experiment/manual_session.py'):
            path = project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('original')
        campaign.mkdir(parents=True)
        current = preparar_sequencia.fingerprint(project)
        (campaign / 'campaign.json').write_text(json.dumps({'source_hashes': current, 'backup_sha256': 'backup'}))
        expected = dict(current)
        files = {name: 'updated ' + name for name in preparar_sequencia.FILES}
        expected.update({name: hashlib.sha256(content.encode()).hexdigest() for name, content in files.items()})
        return project, campaign, {'files': files, 'source_hashes': expected}

    def test_preparation_updates_only_orchestration_and_preserves_plan_with_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, campaign, payload = self.fixture(root)
            plan = campaign / 'plan.json'
            plan.write_text('original plan')
            with patch.object(preparar_sequencia, 'LOCK', root / 'run/campaign.lock'):
                preparar_sequencia.install(project, campaign, payload)
                (campaign / 'blocks').mkdir()
                preparar_sequencia.install(project, campaign, payload)
            self.assertEqual('original plan', plan.read_text())
            metadata = json.loads((campaign / 'campaign.json').read_text())
            self.assertEqual(payload['source_hashes'], metadata['source_hashes'])
            self.assertEqual('backup', metadata['backup_sha256'])
            audit = campaign / metadata['sequence_preparation']
            self.assertEqual('original', (audit / 'load/blocos.py').read_text())
            self.assertEqual('original', (project / 'load/workload.js').read_text())

    def test_preparation_refuses_existing_blocks_or_changes_to_workload(self):
        for scenario in ('blocks', 'workload'):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                project, campaign, payload = self.fixture(root)
                original = (campaign / 'campaign.json').read_bytes()
                if scenario == 'blocks':
                    (campaign / 'blocks').mkdir()
                else:
                    payload['source_hashes']['load/workload.js'] = 'different'
                with patch.object(preparar_sequencia, 'LOCK', root / 'run/campaign.lock'):
                    with self.assertRaises(ValueError):
                        preparar_sequencia.install(project, campaign, payload)
                self.assertEqual('original', (project / 'load/blocos.py').read_text())
                self.assertEqual(original, (campaign / 'campaign.json').read_bytes())

    def test_failed_installation_restores_previous_sources_and_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, campaign, payload = self.fixture(root)
            current = preparar_sequencia.fingerprint(project)
            original = (campaign / 'campaign.json').read_bytes()
            with patch.object(preparar_sequencia, 'LOCK', root / 'run/campaign.lock'), patch.object(preparar_sequencia, 'fingerprint', side_effect=[current, {}]):
                with self.assertRaisesRegex(ValueError, 'Conferência da instalação'):
                    preparar_sequencia.install(project, campaign, payload)
            self.assertEqual('original', (project / 'load/blocos.py').read_text())
            self.assertFalse((project / 'load/intervalo_blocos.py').exists())
            self.assertEqual(original, (campaign / 'campaign.json').read_bytes())

    def test_preparation_refuses_active_campaign(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, campaign, payload = self.fixture(root)
            lock_path = root / 'run/campaign.lock'
            lock_path.parent.mkdir()
            with lock_path.open('a') as lock, patch.object(preparar_sequencia, 'LOCK', lock_path):
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    preparar_sequencia.install(project, campaign, payload)
            self.assertEqual('original', (project / 'load/blocos.py').read_text())

    def failed_attempt(self, campaign):
        first = {'pair_id': 'first-pair', 'run_id': 'first-run', 'sequence': 1}
        (campaign / 'plan.json').write_text(json.dumps({'runs': [first]}))
        block = campaign / 'blocks/bloco-01'
        attempt = block / 'first-pair/tentativa-001'
        run = attempt / 'first-run'
        run.mkdir(parents=True)
        (run / 'run.json').write_text(json.dumps(first))
        (attempt / 'gerador.jsonl').write_text('')
        (block / 'interruption-001.json').write_text(json.dumps({'error': preparar_sequencia.MISSING_BACKUP}))
        return run

    def test_known_failure_before_restore_can_be_repaired_without_erasing_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, campaign, payload = self.fixture(root)
            run = self.failed_attempt(campaign)
            original = (run / 'run.json').read_bytes()
            with patch.object(preparar_sequencia, 'LOCK', root / 'run/campaign.lock'):
                preparar_sequencia.install(project, campaign, payload)
            self.assertEqual(original, (run / 'run.json').read_bytes())
            metadata = json.loads((campaign / 'campaign.json').read_text())
            self.assertFalse(metadata['pre_execution_repair']['measurements_started'])
            backup = campaign / metadata['pre_execution_repair']['backup'] / 'blocks'
            self.assertEqual(original, (backup / 'bloco-01/first-pair/tentativa-001/first-run/run.json').read_bytes())

    def test_repair_is_refused_if_any_hook_or_measurement_artifact_exists(self):
        for name in ('restore.json', 'warmup-summary.json', 'measurement-summary.json', 'complete.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                project, campaign, payload = self.fixture(root)
                run = self.failed_attempt(campaign)
                (run / name).write_text('{}')
                with patch.object(preparar_sequencia, 'LOCK', root / 'run/campaign.lock'):
                    with self.assertRaises(ValueError):
                        preparar_sequencia.install(project, campaign, payload)
                self.assertEqual('original', (project / 'load/blocos.py').read_text())

    def generator_failure(self, project, campaign, payload):
        for name, content in payload['files'].items():
            (project / name).write_text(content)
        current = preparar_sequencia.fingerprint(project)
        (campaign / 'campaign.json').write_text(json.dumps({'source_hashes': current}))
        files = dict(payload['files'])
        files['load/recursos_bloco.py'] += '\ncollector repair'
        expected = dict(current)
        expected['load/recursos_bloco.py'] = hashlib.sha256(files['load/recursos_bloco.py'].encode()).hexdigest()
        run_dir = self.failed_attempt(campaign)
        first = json.loads((run_dir / 'run.json').read_text())
        second = dict(first, run_id='second-run', sequence=2)
        (campaign / 'plan.json').write_text(json.dumps({'runs': [first, second]}))
        (run_dir / 'measurement-summary.json').write_text('{"valid_for_campaign":true}')
        block = campaign / 'blocks/bloco-01'
        (block / 'interruption-001.json').write_text(json.dumps({'error': "Command '['docker', 'stats', '--no-stream', '--format', '{{json .}}', 'ended']' returned non-zero exit status 1."}))
        return {'source_hashes': expected, 'files': files}, run_dir

    def test_collector_repair_preserves_unpaired_measurement_and_requires_repeating_both_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, campaign, payload = self.fixture(root)
            payload, run = self.generator_failure(project, campaign, payload)
            original = (run / 'measurement-summary.json').read_bytes()
            with patch.object(preparar_sequencia, 'LOCK', root / 'run/campaign.lock'):
                preparar_sequencia.install(project, campaign, payload)
            self.assertEqual(original, (run / 'measurement-summary.json').read_bytes())
            metadata = json.loads((campaign / 'campaign.json').read_text())
            self.assertFalse(metadata['generator_collection_repair']['previous_attempts_valid_for_campaign'])
            self.assertEqual(payload['source_hashes'], metadata['source_hashes'])

    def test_collector_repair_refuses_any_completed_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, campaign, payload = self.fixture(root)
            payload, run = self.generator_failure(project, campaign, payload)
            (run.parent.parent / 'complete.json').write_text('{"complete":true}')
            before = (project / 'load/recursos_bloco.py').read_bytes()
            with patch.object(preparar_sequencia, 'LOCK', root / 'run/campaign.lock'):
                with self.assertRaises(ValueError):
                    preparar_sequencia.install(project, campaign, payload)
            self.assertEqual(before, (project / 'load/recursos_bloco.py').read_bytes())


if __name__ == '__main__':
    unittest.main()
