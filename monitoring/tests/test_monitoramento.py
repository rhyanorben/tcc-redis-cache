import importlib.util
import json
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


MONITORING_DIRECTORY = Path(__file__).resolve().parents[1]


def load_module(name):
    specification = importlib.util.spec_from_file_location(name, MONITORING_DIRECTORY / f'{name}.py')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


SUMMARY = load_module('resumir')
COLLECTOR = load_module('coletar')
START = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def timestamp(seconds):
    return (START + timedelta(seconds=seconds)).isoformat()


def application(amount):
    return {
        'process_start_time': 100,
        'cache_instrumented': True,
        'tcc.cache.requests.hit': amount * 4,
        'tcc.cache.requests.miss': amount * 2,
        'tcc.cache.requests.fallback': amount * 2,
        'tcc.cache.errors': amount,
        'tcc.cache.invalidations': amount,
        'tcc.cache.discarded_writes': amount,
    }


def statement(query_id, amount):
    return {'queryid': query_id, 'query': 'SELECT * FROM tcc.pedido WHERE tenant_id = $1',
            **{counter: amount for counter in SUMMARY.SQL_COUNTERS}}


def postgres(amount):
    return {'postmaster_start_time': timestamp(-100), 'stats_reset': timestamp(-100),
            'dealloc': 0, 'statements': [statement('1', amount)]}


def redis(amount):
    return {
        'run_id': 'redis-process-1', 'uptime_in_seconds': 100 + amount,
        'maxmemory': 1073741824, 'maxmemory_policy': 'allkeys-lru',
        'used_memory': 10000 + amount, 'used_memory_dataset': 8000 + amount,
        'used_memory_rss': 12000 + amount,
        **{counter: amount for counter in SUMMARY.REDIS_COUNTERS},
    }


def sample(service, seconds, amount):
    result = {
        'service': service, 'timestamp': timestamp(seconds), 'completed_at': timestamp(seconds + 1),
        'elapsed_seconds': seconds + 10,
        'docker': {'ID': 'container-1', 'CPUPerc': f'{amount}%', 'MemUsage': f'{amount}MiB / 2GiB'},
    }
    result[{'app': 'application', 'postgres': 'postgres', 'redis': 'redis'}[service]] = {
        'app': application, 'postgres': postgres, 'redis': redis,
    }[service](amount)
    return result


def samples(service='app'):
    return [sample(service, index * 5, index + 1) for index in range(3)]


def measured_samples(service='app'):
    return [sample(service, seconds, index + 1)
            for index, seconds in enumerate((-10, -5, 0, 5, 100, 200, 295, 299, 300, 305, 310, 315))]


def measurement_window():
    start = START.timestamp() * 1000
    return {'valid': True, 'scope': 'measurement_only', 'nominal_measurement_seconds': 300,
            'measurement_start_unix_ms': start, 'measurement_end_unix_ms': start + 300000,
            'measurement_completed_unix_ms': start + 310000}


class ResumirTest(unittest.TestCase):
    def test_memory_units(self):
        for value, expected in [('512 B', 512), ('1KiB', 1024), ('2 MiB', 2 * 1024 ** 2),
                                ('1.5GB', 1500000000), ('2GiB', 2 * 1024 ** 3)]:
            with self.subTest(value=value):
                self.assertEqual(expected, SUMMARY.memory_bytes(value))

    def test_rejects_unknown_memory_unit(self):
        with self.assertRaises(ValueError):
            SUMMARY.memory_bytes('128 bananas')

    def test_hit_ratio_includes_fallback(self):
        result = SUMMARY.summarize(samples())
        self.assertEqual(0.5, result['application']['logical_hit_ratio'])
        self.assertEqual(8, result['application']['tcc.cache.requests.hit'])

    def test_no_cache_accesses_has_no_hit_ratio(self):
        result = SUMMARY.summarize_application(application(0), application(0))
        self.assertIsNone(result['logical_hit_ratio'])

    def test_rejects_application_restart(self):
        data = samples()
        data[-1]['application']['process_start_time'] = 101
        with self.assertRaisesRegex(ValueError, 'reiniciou'):
            SUMMARY.summarize(data)

    def test_rejects_application_counter_reset_followed_by_recovery(self):
        data = samples()
        data[1]['application']['tcc.cache.requests.hit'] = 0
        with self.assertRaisesRegex(ValueError, 'diminuiu'):
            SUMMARY.summarize(data)

    def test_rejects_application_identity_missing(self):
        data = samples()
        del data[1]['application']['process_start_time']
        with self.assertRaisesRegex(ValueError, 'Identificação'):
            SUMMARY.summarize(data)

    def test_rejects_cache_instrumentation_change(self):
        data = samples()
        data[1]['application']['cache_instrumented'] = False
        with self.assertRaisesRegex(ValueError, 'instrumentação'):
            SUMMARY.summarize(data)

    def test_new_postgres_query_starts_at_zero(self):
        before = postgres(2)
        after = postgres(5)
        after['statements'].append(statement('2', 7))
        result = SUMMARY.summarize_postgres(before, after)
        self.assertEqual(10, result['totals']['calls'])
        self.assertEqual(7, result['statements'][1]['calls'])

    def test_rejects_disappearing_postgres_query(self):
        data = samples('postgres')
        data[1]['postgres']['statements'] = []
        with self.assertRaisesRegex(ValueError, 'desapareceu'):
            SUMMARY.summarize(data)

    def test_rejects_postgres_restart(self):
        data = samples('postgres')
        data[1]['postgres']['postmaster_start_time'] = timestamp(-50)
        with self.assertRaisesRegex(ValueError, 'reiniciou'):
            SUMMARY.summarize(data)

    def test_rejects_postgres_statistics_reset_followed_by_recovery(self):
        data = samples('postgres')
        data[1]['postgres']['stats_reset'] = timestamp(1)
        with self.assertRaisesRegex(ValueError, 'reiniciadas'):
            SUMMARY.summarize(data)

    def test_rejects_postgres_statistics_eviction(self):
        data = samples('postgres')
        data[-1]['postgres']['dealloc'] = 1
        with self.assertRaisesRegex(ValueError, 'descartadas'):
            SUMMARY.summarize(data)

    def test_rejects_postgres_counter_reset_followed_by_recovery(self):
        data = samples('postgres')
        data[1]['postgres']['statements'][0]['calls'] = 0
        with self.assertRaisesRegex(ValueError, 'diminuiu'):
            SUMMARY.summarize(data)

    def test_rejects_redis_restart(self):
        data = samples('redis')
        data[1]['redis']['run_id'] = 'redis-process-2'
        with self.assertRaisesRegex(ValueError, 'reiniciou'):
            SUMMARY.summarize(data)

    def test_rejects_redis_memory_change_followed_by_recovery(self):
        data = samples('redis')
        data[1]['redis']['maxmemory'] = 268435456
        with self.assertRaisesRegex(ValueError, 'memória'):
            SUMMARY.summarize(data)

    def test_rejects_redis_counter_reset_followed_by_recovery(self):
        data = samples('redis')
        data[1]['redis']['keyspace_hits'] = 0
        with self.assertRaisesRegex(ValueError, 'diminuiu'):
            SUMMARY.summarize(data)

    def test_redis_memory_uses_selected_resource_samples(self):
        result = SUMMARY.summarize(measured_samples('redis'), measurement_window())
        self.assertEqual(10003, result['redis']['used_memory']['minimum'])
        self.assertEqual(10008, result['redis']['used_memory']['maximum'])
        self.assertEqual(9, result['redis']['counters']['keyspace_hits'])

    def test_rejects_container_replacement_in_intermediate_sample(self):
        data = samples()
        data[1]['docker']['ID'] = 'replacement'
        with self.assertRaisesRegex(ValueError, 'substituído'):
            SUMMARY.summarize(data)

    def test_rejects_missing_counter(self):
        data = samples()
        del data[-1]['application']['tcc.cache.requests.hit']
        with self.assertRaisesRegex(ValueError, 'ausente'):
            SUMMARY.summarize(data)

    def test_rejects_collection_error(self):
        data = samples()
        data[1]['error'] = 'TimeoutError'
        with self.assertRaisesRegex(ValueError, 'falhas'):
            SUMMARY.summarize(data)

    def test_rejects_mixed_services(self):
        data = samples()
        data[1]['service'] = 'redis'
        with self.assertRaisesRegex(ValueError, 'Mistura'):
            SUMMARY.summarize(data)

    def test_rejects_non_increasing_elapsed_time(self):
        data = samples()
        data[1]['elapsed_seconds'] = data[0]['elapsed_seconds']
        with self.assertRaisesRegex(ValueError, 'ordem'):
            SUMMARY.summarize(data)

    def test_resource_window_is_nominal_but_counters_include_drain(self):
        data = measured_samples()
        result = SUMMARY.summarize(data, measurement_window())
        self.assertEqual(6, result['resource_sample_count'])
        self.assertEqual(3, result['docker_cpu_percent']['minimum'])
        self.assertEqual(8, result['docker_cpu_percent']['maximum'])
        self.assertEqual(timestamp(-5), result['started_at'])
        self.assertEqual(timestamp(311), result['ended_at'])
        self.assertEqual(36, result['application']['tcc.cache.requests.hit'])
        self.assertTrue(result['counter_window']['requires_quiet_margins'])

    def test_rejects_missing_counter_coverage_after_drain(self):
        data = measured_samples()[:-2]
        with self.assertRaisesRegex(ValueError, 'cobre'):
            SUMMARY.summarize(data, measurement_window())

    def test_rejects_excessive_counter_margin(self):
        data = measured_samples()
        data[1]['timestamp'] = timestamp(-20)
        data[1]['completed_at'] = timestamp(-19)
        data[0]['timestamp'] = timestamp(-25)
        data[0]['completed_at'] = timestamp(-24)
        with self.assertRaisesRegex(ValueError, 'Margem'):
            SUMMARY.summarize(data, measurement_window())

    def test_rejects_naive_clock_timestamp(self):
        data = measured_samples()
        data[3]['timestamp'] = '2026-10-17T12:00:05'
        with self.assertRaisesRegex(ValueError, 'fuso'):
            SUMMARY.summarize(data, measurement_window())

    def test_rejects_naive_timestamp_without_measurement_window(self):
        data = samples()
        data[1]['timestamp'] = '2026-10-17T12:00:05'
        with self.assertRaises(ValueError):
            SUMMARY.summarize(data)

    def test_rejects_clock_regression(self):
        data = samples()
        data[1]['timestamp'] = timestamp(-10)
        data[1]['completed_at'] = timestamp(-9)
        with self.assertRaises(ValueError):
            SUMMARY.summarize(data)

    def test_rejects_sample_completion_before_start(self):
        data = samples()
        data[1]['completed_at'] = timestamp(4)
        with self.assertRaises(ValueError):
            SUMMARY.summarize(data)

    def test_rejects_non_300_second_measurement(self):
        window = measurement_window()
        window['measurement_end_unix_ms'] -= 1000
        with self.assertRaises(ValueError):
            SUMMARY.summarize(measured_samples(), window)

    def test_rejects_failed_k6_execution(self):
        window = measurement_window()
        window['valid'] = False
        with self.assertRaises(ValueError):
            SUMMARY.summarize(measured_samples(), window)


class ColetarTest(unittest.TestCase):
    def test_database_collection_filters_application_user(self):
        self.assertIn("rolname = 'tcc_app'", COLLECTOR.SQL_STATISTICS)
        self.assertIn('pg_stat_statements_info', COLLECTOR.SQL_STATISTICS)
        with patch.object(COLLECTOR, 'execute', return_value=json.dumps(postgres(1))) as execute:
            result = COLLECTOR.postgres_statistics(Path('/infra/postgres/compose.yaml'))
        self.assertEqual(1, result['statements'][0]['calls'])
        arguments = execute.call_args.args[0]
        self.assertIn('tcc_monitor', arguments)
        self.assertNotIn('-W', arguments)

    def test_redis_collection_keeps_secret_inside_container(self):
        info = '# Server\r\nrun_id:abc123\r\nmaxmemory:1073741824\r\nused_memory:1000\r\n'
        with patch.object(COLLECTOR, 'execute', return_value=info) as execute:
            result = COLLECTOR.redis_statistics(Path('/infra/redis/compose.yaml'))
        self.assertEqual('abc123', result['run_id'])
        self.assertEqual(1073741824, result['maxmemory'])
        arguments = execute.call_args.args[0]
        self.assertIn('/run/secrets/redis_password', arguments[-1])
        self.assertNotIn('redis_password', result)

    def test_execute_does_not_expose_failure_output(self):
        failure = subprocess.CompletedProcess(['docker'], 1, 'secret-value', 'secret-value')
        with patch.object(COLLECTOR.subprocess, 'run', return_value=failure):
            with self.assertRaises(RuntimeError) as error:
                COLLECTOR.execute(['docker', 'exec'])
        self.assertNotIn('secret-value', str(error.exception))


if __name__ == '__main__':
    unittest.main()
