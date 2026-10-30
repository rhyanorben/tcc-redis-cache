import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / 'coletar.py'
specification = importlib.util.spec_from_file_location('coletar_cutoff', source)
collector = importlib.util.module_from_spec(specification)
specification.loader.exec_module(collector)


class CutoffTest(unittest.TestCase):
    def test_restore_cutoff_preserves_application_role_and_database_filter(self):
        with patch.object(collector, 'execute', return_value='{}') as execute:
            collector.postgres_statistics(Path('/tmp/compose.yaml'), 'tcc_experimento', '2026-10-23T12:00:00+00:00')
        command = execute.call_args.args[0]
        self.assertIn('tcc_experimento', command)
        self.assertIn("rolname = 'tcc_app'", command[-1])
        self.assertIn("stats_since >= '2026-10-23T12:00:00+00:00'", command[-1])

    def test_cutoff_rejects_missing_timezone_or_sql_content(self):
        for value in ('2026-10-23T12:00:00', "2026-10-23';DROP DATABASE tcc;"):
            with patch.object(collector, 'execute') as execute:
                with self.assertRaises(ValueError):
                    collector.postgres_statistics(Path('/tmp/compose.yaml'), 'tcc_experimento', value)
                execute.assert_not_called()
