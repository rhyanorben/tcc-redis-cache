import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from executar import validate_plan
from outcomes import validate_outcomes
from planejar import NAVIGATION, build_plan
from resumir import consolidate, load_runs
from test_load import results_fixture
from test_outcomes import summary_fixture, write_run


class NavigationProtocolTests(unittest.TestCase):
    def test_pagination_counters_are_validated_and_available_for_analysis(self):
        summary = summary_fixture(3)
        validate_outcomes(summary)
        with tempfile.TemporaryDirectory() as temporary:
            write_run(Path(temporary), summary)
            result = next(iter(load_runs(Path(temporary)).values()))
        self.assertEqual(3, result['protocol_version'])
        self.assertEqual(NAVIGATION, result['navigation_config'])
        self.assertEqual(10, result['metrics']['navigation.reads.first'])
        self.assertNotIn('navigation.latency_ms.last.avg', result['metrics'])

    def test_missing_navigation_wrong_weights_and_inconsistent_counts_are_rejected(self):
        for field, value in (
                ('config', {}), ('forward_visits', -1), ('reverse_visits', 20),
                ('reads', {'first': 2, 'intermediate': 0, 'last': 0}),
                ('errors', {'first': 0, 'intermediate': 0, 'last': 0}),
                ('latency_ms', {'first': None, 'intermediate': None, 'last': None})):
            with self.subTest(field=field):
                summary = summary_fixture(3)
                summary['navigation'][field] = value
                with self.assertRaises(ValueError):
                    validate_outcomes(summary)
        summary = summary_fixture(3)
        del summary['navigation']
        with self.assertRaisesRegex(ValueError, 'Navegação'):
            validate_outcomes(summary)

    def test_old_results_remain_readable_but_protocols_cannot_be_combined(self):
        self.assertEqual(2, consolidate(results_fixture())['protocol_version'])
        mixed = results_fixture()
        next(iter(mixed.values()))['protocol_version'] = 3
        with self.assertRaisesRegex(ValueError, 'protocolos diferentes'):
            consolidate(mixed)

    def test_navigation_parameters_cannot_be_mixed_and_unvisited_latency_is_not_zero(self):
        runs = results_fixture()
        for result in runs.values():
            result.update(protocol_version=3, navigation_config=copy.deepcopy(NAVIGATION))
        last = runs[('90-10', 25, 'on', 1)]
        last['metrics']['navigation.latency_ms.last.avg'] = 90
        result = consolidate(runs)
        self.assertEqual(3, result['protocol_version'])
        group = next(group for group in result['groups'] if group['cache_mode'] == 'on')
        self.assertEqual(1, group['metrics']['navigation.latency_ms.last.avg']['n'])
        self.assertEqual(90, group['metrics']['navigation.latency_ms.last.avg']['mean'])
        last['navigation_config']['forward_visit_ratio'] = 0.5
        with self.assertRaisesRegex(ValueError, 'configurações de navegação diferentes'):
            consolidate(runs)

    def test_old_plan_and_modified_navigation_are_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / 'manifest.json'
            manifest.write_text(json.dumps({'schema_version': 1, 'active_company_count': 25}))
            plan = build_plan(manifest, 1)
            validate_plan(plan, manifest)
            plan['protocol_version'] = 2
            with self.assertRaisesRegex(ValueError, 'campanha nova'):
                validate_plan(plan, manifest)
            plan['protocol_version'] = 3
            plan['navigation']['forward_visit_ratio'] = 0.5
            with self.assertRaisesRegex(ValueError, 'campanha nova'):
                validate_plan(plan, manifest)


if __name__ == '__main__':
    unittest.main()
