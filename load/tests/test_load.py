import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

LOAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOAD))
from criar_manifesto import build_manifest
from executar import validate_hooks, validate_plan, validate_url
from planejar import build_plan
from resumir import consolidate, load_runs, run_metrics


def manifest_rows():
    for company in range(100):
        for slot in range(20):
            yield {
                'tenant_id': str(1001 + company * 2),
                'empresa_nome': f'TCC-exp-001 Empresa {company + 1}',
                'total_clientes': '5000', 'total_pedidos': '20000', 'total_itens': '60000',
                'slot': str(slot), 'pedido_id': str(50001 + company * 100 + slot),
                'pedido_status': 'ABERTO',
            }


class ManifestTests(unittest.TestCase):
    def test_real_identifiers_and_expected_counts(self):
        manifest = build_manifest(manifest_rows(), 'exp-001')
        self.assertEqual('1001', manifest['companies'][0]['tenant_id'])
        self.assertEqual('50001', manifest['companies'][0]['write_orders'][0]['id'])
        self.assertEqual(100, len(manifest['companies']))

    def test_rejects_incomplete_counts_status_and_duplicate_orders(self):
        rows = list(manifest_rows())
        for field, value in [('total_itens', '20000'), ('pedido_status', 'CANCELADO'), ('pedido_id', rows[0]['pedido_id'])]:
            changed = copy.deepcopy(rows)
            changed[1][field] = value
            with self.assertRaises(ValueError):
                build_manifest(changed, 'exp-001')
        with self.assertRaises(ValueError):
            build_manifest(rows[:-1], 'exp-001')


class PlanTests(unittest.TestCase):
    def test_matrix_is_deterministic_paired_and_validated(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / 'manifest.json'
            manifest.write_text(json.dumps(build_manifest(manifest_rows(), 'exp-001')), encoding='utf-8')
            plan = build_plan(manifest, 20261017)
            self.assertEqual(plan, build_plan(manifest, 20261017))
            self.assertEqual(200, len(plan['runs']))
            self.assertNotEqual(plan['runs'], build_plan(manifest, 99)['runs'])
            validate_plan(plan, manifest)
            for index in range(0, 200, 2):
                left, right = plan['runs'][index:index + 2]
                self.assertEqual(left['seed'], right['seed'])
                self.assertEqual(left['pair_id'], right['pair_id'])
                self.assertNotEqual(left['cache_mode'], right['cache_mode'])
            manifest.write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError):
                validate_plan(plan, manifest)

    def test_uninstalled_hooks_and_external_destinations_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_hooks(None)
        with self.assertRaises(ValueError):
            validate_hooks(LOAD / 'hooks.example')
        for value in ['https://10.10.10.10:8080', 'http://example.com', 'http://10.10.10.10@elsewhere',
                      'http://localhost:8080/path', 'http://localhost:8080?redirect=1']:
            with self.assertRaises(ValueError):
                validate_url(value)
        self.assertEqual('http://10.10.10.10:8080', validate_url('http://10.10.10.10:8080/'))


def results_fixture():
    runs = {}
    for mode in ('off', 'on'):
        for repetition in range(1, 6):
            runs[('90-10', 25, mode, repetition)] = {
                'run': {'seed': str(repetition), 'pair_id': f'pair-{repetition}'},
                'completion': {'complete': True, 'backup_sha256': 'abc', 'manifest_sha256': 'def'},
                'metrics': {'throughput_requests_per_second': repetition * (10 if mode == 'off' else 15),
                            'read_latency_ms.p(95)': repetition * (20 if mode == 'off' else 10),
                            'write_errors': 0},
            }
    return runs


class SummaryTests(unittest.TestCase):
    def test_resource_metrics_follow_monitoring_summary_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'monitoring').mkdir()
            window = {'measurement_start_unix_ms': 1000, 'measurement_end_unix_ms': 301000,
                      'measurement_completed_unix_ms': 302000}
            for service in ('app', 'postgres', 'redis'):
                monitor = {
                    'service': service, 'scope': 'measurement_resources_with_bracketed_counters',
                    'measurement_window': window,
                    'docker_cpu_percent': {'mean': 25, 'minimum': 10, 'maximum': 50},
                    'docker_memory_bytes': {'mean': 2048, 'minimum': 1024, 'maximum': 4096},
                }
                if service == 'app':
                    monitor['application'] = {'logical_hit_ratio': 0.75, 'tcc.cache.requests.hit': 30}
                path = directory / 'monitoring' / f'{service}-summary.json'
                path.write_text(json.dumps(monitor), encoding='utf-8')
            metrics = run_metrics(directory, window)
            self.assertEqual(25, metrics['app.resources.docker_cpu_percent.mean'])
            self.assertEqual(4096, metrics['postgres.resources.docker_memory_bytes.maximum'])
            self.assertEqual(0.75, metrics['app.application.logical_hit_ratio'])
            (directory / 'monitoring' / 'redis-summary.json').unlink()
            with self.assertRaisesRegex(ValueError, 'Monitoramento obrigatório'):
                run_metrics(directory, window)

    def test_missing_metrics_between_repetitions_are_rejected(self):
        different = results_fixture()
        del different[('90-10', 25, 'on', 5)]['metrics']['read_latency_ms.p(95)']
        with self.assertRaisesRegex(ValueError, 'métricas diferentes'):
            consolidate(different)

    def test_five_repetitions_and_paired_percentages(self):
        result = consolidate(results_fixture())
        self.assertEqual(2, len(result['groups']))
        metrics = result['pairs'][0]['metrics']
        throughput = metrics['throughput_requests_per_second']['percent_on_minus_off_over_off']
        self.assertEqual(5, throughput['n'])
        self.assertEqual(50, throughput['mean'])
        self.assertEqual(0, throughput['sample_standard_deviation'])
        self.assertEqual(-50, metrics['read_latency_ms.p(95)']['percent_on_minus_off_over_off']['mean'])
        self.assertIsNone(metrics['write_errors']['percent_on_minus_off_over_off'])
        self.assertIn('não é o percentil global', result['latency_note'])

    def test_rejects_missing_repetition_or_different_backup(self):
        incomplete = results_fixture()
        del incomplete[('90-10', 25, 'on', 5)]
        with self.assertRaises(ValueError):
            consolidate(incomplete)
        different = results_fixture()
        different[('90-10', 25, 'on', 5)]['completion']['backup_sha256'] = 'other'
        with self.assertRaises(ValueError):
            consolidate(different)

    def test_smoke_summary_cannot_be_consolidated(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'smoke'
            directory.mkdir()
            (directory / 'measurement-summary.json').write_text(json.dumps({
                'scope': 'measurement_only', 'valid': True, 'smoke_test': True, 'valid_for_campaign': False,
            }), encoding='utf-8')
            (directory / 'complete.json').write_text('{"complete":true}', encoding='utf-8')
            (directory / 'run.json').write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Smoke'):
                load_runs(Path(temporary))


if __name__ == '__main__':
    unittest.main()
