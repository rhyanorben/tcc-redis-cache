import base64
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / 'hooks.vm/dispatch.py'
specification = importlib.util.spec_from_file_location('dispatch_partial', source)
hooks = importlib.util.module_from_spec(specification)
specification.loader.exec_module(hooks)


class PartialMonitoringTest(unittest.TestCase):
    def test_raw_data_from_every_service_survives_missing_k6_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'monitoring').mkdir()
            environment = {'RUN_DIR': str(directory), 'RUN_ID': 'case', 'MEASUREMENT_SUMMARY': str(directory / 'missing.json')}
            raw = b'{"sample":1}\n'
            with patch.dict(os.environ, environment), patch.object(hooks, 'remote', return_value={'jsonl': base64.b64encode(raw).decode()}):
                with self.assertRaises(ValueError):
                    hooks.monitor_stop()
            for service in hooks.SERVICES:
                self.assertEqual(raw, (directory / f'monitoring/{service}.jsonl').read_bytes())
