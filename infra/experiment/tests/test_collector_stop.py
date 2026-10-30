import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

source = Path(__file__).resolve().parents[1] / 'remote_agent.py'
specification = importlib.util.spec_from_file_location('agent_stop', source)
agent_module = importlib.util.module_from_spec(specification)
specification.loader.exec_module(agent_module)


def process_stat(state='S', start='12345', name='python3'):
    fields = [state, *['0'] * 18, start, '0']
    return '123 (' + name + ') ' + ' '.join(fields)


class CollectorStopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        (self.directory / 'process.json').write_text(json.dumps({'pid': 123, 'start_ticks': '12345'}))
        self.agent = agent_module.Agent.__new__(agent_module.Agent)
        self.agent.config = {'collector': '/opt/tcc-experiment/coletar.py'}
        self.process = Mock()
        self.statistics = Mock()
        self.command = Mock()
        self.process.__truediv__ = Mock(side_effect=lambda name: {'stat': self.statistics, 'cmdline': self.command}[name])
        self.command.read_bytes.return_value = b'python3\0/opt/tcc-experiment/coletar.py\0'
        self.kill = self.enterContext(patch.object(agent_module.os, 'kill'))
        self.enterContext(patch.object(agent_module, 'Path', return_value=self.process))
        self.sleep = self.enterContext(patch.object(agent_module.time, 'sleep'))
        self.monotonic = self.enterContext(patch.object(agent_module.time, 'monotonic', return_value=0))

    def test_waits_for_termination_after_sigterm(self):
        self.statistics.read_text.side_effect = [process_stat(), process_stat(), process_stat(), FileNotFoundError()]
        self.agent.stop_collector(self.directory)
        self.kill.assert_called_once_with(123, agent_module.signal.SIGTERM)
        self.sleep.assert_called_once_with(0.1)

    def test_zombie_is_already_stopped(self):
        self.statistics.read_text.return_value = process_stat('Z')
        self.agent.stop_collector(self.directory)
        self.kill.assert_not_called()
        self.command.read_bytes.assert_not_called()

    def test_zombie_after_sigterm_confirms_stop_without_waiting_for_reaping(self):
        self.statistics.read_text.side_effect = [process_stat(), process_stat(), process_stat('Z')]
        self.agent.stop_collector(self.directory)
        self.kill.assert_called_once_with(123, agent_module.signal.SIGTERM)
        self.sleep.assert_not_called()

    def test_missing_process_is_already_stopped(self):
        self.statistics.read_text.side_effect = FileNotFoundError()
        self.agent.stop_collector(self.directory)
        self.kill.assert_not_called()

    def test_initial_pid_reuse_never_signals_unrelated_process(self):
        self.statistics.read_text.return_value = process_stat(start='54321')
        self.agent.stop_collector(self.directory)
        self.kill.assert_not_called()
        self.command.read_bytes.assert_not_called()

    def test_pid_reuse_during_command_check_never_signals_replacement(self):
        self.statistics.read_text.side_effect = [process_stat(), process_stat(start='54321')]
        self.agent.stop_collector(self.directory)
        self.kill.assert_not_called()

    def test_pid_reuse_after_sigterm_confirms_original_process_stopped(self):
        self.statistics.read_text.side_effect = [process_stat(), process_stat(), process_stat(start='54321')]
        self.agent.stop_collector(self.directory)
        self.kill.assert_called_once_with(123, agent_module.signal.SIGTERM)
        self.sleep.assert_not_called()

    def test_active_process_without_collector_command_is_rejected(self):
        self.statistics.read_text.return_value = process_stat()
        self.command.read_bytes.return_value = b'python3\0outro-processo.py\0'
        with self.assertRaisesRegex(RuntimeError, 'PID não pertence ao coletor'):
            self.agent.stop_collector(self.directory)
        self.kill.assert_not_called()

    def test_process_still_active_after_ten_seconds_fails_confirmation(self):
        self.statistics.read_text.return_value = process_stat()
        self.monotonic.side_effect = [0, 0, 10]
        with self.assertRaisesRegex(RuntimeError, 'não encerrou após 10 segundos'):
            self.agent.stop_collector(self.directory)
        self.kill.assert_called_once_with(123, agent_module.signal.SIGTERM)
        self.sleep.assert_called_once_with(0.1)

    def test_process_disappearing_before_sigterm_is_already_stopped(self):
        self.statistics.read_text.return_value = process_stat()
        self.kill.side_effect = ProcessLookupError()
        self.agent.stop_collector(self.directory)
        self.kill.assert_called_once_with(123, agent_module.signal.SIGTERM)
        self.monotonic.assert_not_called()

    def test_process_name_with_spaces_and_closing_parenthesis_keeps_pid_guard(self):
        self.statistics.read_text.side_effect = [process_stat(name='python ) renamed'), process_stat(name='python ) renamed'), process_stat('Z', name='python ) renamed')]
        self.agent.stop_collector(self.directory)
        self.kill.assert_called_once_with(123, agent_module.signal.SIGTERM)


if __name__ == '__main__':
    unittest.main()
