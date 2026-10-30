import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import recursos_bloco


def result(code, output=''):
    return subprocess.CompletedProcess(['docker', 'stats'], code, stdout=output, stderr='')


class GeneratorResourcesTest(unittest.TestCase):
    def test_container_ending_between_discovery_and_sampling_is_recorded_without_failure(self):
        with patch.object(recursos_bloco, 'running_generators', side_effect=[['ended'], []]), patch.object(recursos_bloco.subprocess, 'run', return_value=result(1)):
            stats, ended = recursos_bloco.generator_stats()
        self.assertEqual([], stats)
        self.assertEqual(['ended'], ended)

    def test_other_running_container_is_sampled_after_one_ends(self):
        sample = {'ID': 'running', 'CPUPerc': '20%'}
        with patch.object(recursos_bloco, 'running_generators', side_effect=[['ended', 'running'], ['running']]), patch.object(recursos_bloco.subprocess, 'run', side_effect=[result(1), result(0, json.dumps(sample))]) as collect:
            stats, ended = recursos_bloco.generator_stats()
        self.assertEqual([sample], stats)
        self.assertEqual(['ended'], ended)
        self.assertEqual('running', collect.call_args.args[0][-1])
        self.assertNotIn('ended', collect.call_args.args[0])

    def test_stats_error_for_a_still_running_container_is_not_hidden(self):
        with patch.object(recursos_bloco, 'running_generators', return_value=['running']), patch.object(recursos_bloco.subprocess, 'run', return_value=result(1)):
            with self.assertRaises(subprocess.CalledProcessError):
                recursos_bloco.generator_stats()

    def test_docker_daemon_failure_or_timeout_still_stops_collection(self):
        with patch.object(recursos_bloco, 'running_generators', side_effect=[['running'], subprocess.CalledProcessError(1, ['docker', 'ps'])]), patch.object(recursos_bloco.subprocess, 'run', return_value=result(1)):
            with self.assertRaises(subprocess.CalledProcessError):
                recursos_bloco.generator_stats()
        with patch.object(recursos_bloco, 'running_generators', return_value=['running']), patch.object(recursos_bloco.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['docker', 'stats'], 15)):
            with self.assertRaises(subprocess.TimeoutExpired):
                recursos_bloco.generator_stats()

    def test_no_generator_between_phases_does_not_invoke_stats(self):
        with patch.object(recursos_bloco, 'running_generators', return_value=[]), patch.object(recursos_bloco.subprocess, 'run') as collect:
            self.assertEqual(([], []), recursos_bloco.generator_stats())
            collect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
