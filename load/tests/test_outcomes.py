import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

LOAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOAD))
from outcomes import validate_outcomes
from resumir import consolidate, load_runs
from test_load import results_fixture


def latency():
    return {'avg': 50, 'min': 20, 'med': 40, 'max': 90, 'p(95)': 80, 'p(99)': 89}


def summary_fixture():
    summary = {
        'schema_version': 2, 'protocol_version': 2,
        'scope': 'measurement_only', 'valid': True, 'valid_for_campaign': True, 'smoke_test': False,
        'run_id': '90-10-vu025-r1-on', 'profile': '90-10', 'virtual_users': 25, 'seed': 'seed', 'cache_mode': 'on',
        'measurement_start_unix_ms': 1000, 'measurement_end_unix_ms': 301000,
        'measurement_completed_unix_ms': 302000, 'nominal_measurement_seconds': 300,
        'reads': 10, 'writes': 5, 'requests': 15, 'errors': 4, 'read_errors': 2, 'write_errors': 2,
        'read_attempts': 10, 'write_attempts': 5, 'attempts': 15,
        'read_successes': 8, 'write_successes': 3, 'successes': 11,
        'read_rejections': 1, 'write_rejections': 2, 'rejections': 3, 'write_uncertain': 0,
        'response_contract_errors': 0,
        'read_latency_ms': latency(), 'write_latency_ms': latency(),
        'read_success_latency_ms': latency(), 'write_success_latency_ms': latency(),
    }
    update_rates(summary)
    return summary


def update_rates(summary):
    summary.update({
        'throughput_requests_per_second': summary['requests'] / 300,
        'successful_requests_per_second': summary['successes'] / 300,
        'successful_read_requests_per_second': summary['read_successes'] / 300,
        'successful_write_requests_per_second': summary['write_successes'] / 300,
        'error_ratio': summary['errors'] / summary['requests'],
        'observed_write_ratio': summary['writes'] / summary['requests'],
    })


def write_run(root, summary):
    directory = root / summary['run_id']
    directory.mkdir()
    (directory / 'monitoring').mkdir()
    (directory / 'measurement-summary.json').write_text(json.dumps(summary))
    run = {name: summary[name] for name in ('run_id', 'profile', 'virtual_users', 'seed', 'cache_mode')}
    run['repetition'] = 1
    (directory / 'run.json').write_text(json.dumps(run))
    (directory / 'complete.json').write_text(json.dumps({'complete': True, 'backup_sha256': 'abc', 'manifest_sha256': 'def'}))
    for service in ('app', 'postgres', 'redis'):
        monitor = {
            'service': service, 'scope': 'measurement_resources_with_bracketed_counters',
            'measurement_window': {name: summary[name] for name in (
                'measurement_start_unix_ms', 'measurement_end_unix_ms', 'measurement_completed_unix_ms')},
            'docker_cpu_percent': {'mean': 25, 'minimum': 10, 'maximum': 50},
            'docker_memory_bytes': {'mean': 2048, 'minimum': 1024, 'maximum': 4096},
        }
        (directory / 'monitoring' / f'{service}-summary.json').write_text(json.dumps(monitor))


class OutcomeTests(unittest.TestCase):
    def test_safe_rejections_are_errors_and_do_not_invalidate_completed_measurement(self):
        summary = summary_fixture()
        validate_outcomes(summary)
        with tempfile.TemporaryDirectory() as temporary:
            write_run(Path(temporary), summary)
            result = next(iter(load_runs(Path(temporary)).values()))
            self.assertEqual(2, result['metrics']['write_errors'])
            self.assertEqual(2, result['metrics']['write_rejections'])
            self.assertEqual(11 / 300, result['metrics']['successful_requests_per_second'])
            self.assertEqual(50, result['metrics']['write_success_latency_ms.avg'])

    def test_old_protocols_and_schema_versions_are_rejected(self):
        for field in ('schema_version', 'protocol_version'):
            summary = summary_fixture()
            summary[field] = 1
            with self.assertRaisesRegex(ValueError, 'não misture'):
                validate_outcomes(summary)
        with tempfile.TemporaryDirectory() as temporary:
            summary = summary_fixture()
            summary['schema_version'] = 1
            write_run(Path(temporary), summary)
            with self.assertRaisesRegex(ValueError, 'não misture'):
                load_runs(Path(temporary))

    def test_missing_non_integer_negative_and_inconsistent_counts_are_rejected(self):
        changes = (
            {'writes': -1}, {'reads': True}, {'attempts': None}, {'write_errors': 1}, {'successes': 10},
            {'requests': 14}, {'errors': 3}, {'read_attempts': 9}, {'write_attempts': 4},
            {'read_successes': 7}, {'write_successes': 2}, {'rejections': 1}, {'read_rejections': 3},
        )
        for fields in changes:
            summary = summary_fixture()
            summary.update(fields)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate_outcomes(summary)

    def test_uncertain_writes_and_contract_errors_remain_invalid(self):
        summary = summary_fixture()
        summary.update({'write_uncertain': 1, 'write_rejections': 1, 'rejections': 2})
        with self.assertRaisesRegex(ValueError, 'Falha incerta'):
            validate_outcomes(summary)
        summary = summary_fixture()
        summary['response_contract_errors'] = 1
        with self.assertRaisesRegex(ValueError, 'violação de contrato'):
            validate_outcomes(summary)

    def test_non_finite_or_inconsistent_rates_and_latency_are_rejected(self):
        for field, value in (
                ('successful_requests_per_second', 1), ('error_ratio', math.nan),
                ('throughput_requests_per_second', math.inf), ('successful_write_requests_per_second', True),
                ('read_success_latency_ms', None), ('write_success_latency_ms', {'avg': 10})):
            summary = summary_fixture()
            summary[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_outcomes(summary)
        summary = summary_fixture()
        summary['read_success_latency_ms']['p(95)'] = math.inf
        with self.assertRaisesRegex(ValueError, 'Latência inválida'):
            validate_outcomes(summary)

    def test_zero_success_has_no_success_latency_and_is_preserved(self):
        summary = summary_fixture()
        summary.update({'write_successes': 0, 'successes': 8, 'write_errors': 5,
                        'errors': 7, 'write_rejections': 5, 'rejections': 6,
                        'write_success_latency_ms': None})
        update_rates(summary)
        validate_outcomes(summary)
        summary['write_success_latency_ms'] = latency()
        with self.assertRaisesRegex(ValueError, 'sem requisições'):
            validate_outcomes(summary)

    def test_success_latency_uses_only_available_repetitions_and_paired_observations(self):
        runs = results_fixture()
        for key, result in runs.items():
            if key != ('90-10', 25, 'on', 5):
                result['metrics']['write_success_latency_ms.p(95)'] = 50
        result = consolidate(runs)
        group = next(group for group in result['groups'] if group['cache_mode'] == 'on')
        metric = 'write_success_latency_ms.p(95)'
        self.assertEqual(4, group['metrics'][metric]['n'])
        self.assertEqual([5], group['metrics_missing_repetitions'][metric])
        paired = result['pairs'][0]['metrics'][metric]
        self.assertEqual(4, paired['difference_on_minus_off']['n'])
        self.assertEqual([5], paired['missing_repetitions'])
        self.assertEqual(0, paired['difference_on_minus_off']['mean'])

    def test_absent_successes_are_not_imputed_as_zero_latency(self):
        runs = results_fixture()
        metric = 'write_success_latency_ms.p(95)'
        for key, result in runs.items():
            if key[2] == 'off':
                result['metrics'][metric] = 50
        result = consolidate(runs)
        paired = result['pairs'][0]['metrics'][metric]
        self.assertIsNone(paired['difference_on_minus_off'])
        self.assertIsNone(paired['percent_on_minus_off_over_off'])
        self.assertEqual([1, 2, 3, 4, 5], paired['missing_repetitions'])
        self.assertIn(metric, result['pairs'][0]['metrics_unavailable_in_one_mode'])

    def test_a_zero_baseline_does_not_produce_a_partial_percentage_for_other_metrics(self):
        runs = results_fixture()
        runs[('90-10', 25, 'off', 2)]['metrics']['throughput_requests_per_second'] = 0
        metric = consolidate(runs)['pairs'][0]['metrics']['throughput_requests_per_second']
        self.assertIsNone(metric['percent_on_minus_off_over_off'])
        self.assertEqual('baseline_zero', metric['percent_unavailable_reason'])


if __name__ == '__main__':
    unittest.main()
