import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

source = Path(__file__).resolve().parents[1] / 'remote_agent.py'
specification = importlib.util.spec_from_file_location('remote_agent', source)
agent_module = importlib.util.module_from_spec(specification)
specification.loader.exec_module(agent_module)


class ExperimentGuardsTest(unittest.TestCase):
    def test_run_id_rejects_paths_and_shell_syntax(self):
        for value in ('../dados', 'ensaio/1', '', 'ensaio;true', 'ensaio 1', 'á'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                agent_module.valid_run_id(value)

    def test_configuration_rejects_original_database(self):
        with patch.object(agent_module.socket, 'gethostname', return_value='tcc-postgres'):
            with self.assertRaises(ValueError):
                agent_module.Agent({'service': 'postgres', 'database': 'tcc'})

    def test_restore_rejects_database_without_experiment_marker(self):
        agent = agent_module.Agent.__new__(agent_module.Agent)
        agent.sql = Mock(return_value='')
        with patch.object(agent_module.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                agent.restore('a' * 64)
            run.assert_not_called()

    def test_restore_rejects_hash_before_database_changes(self):
        agent = agent_module.Agent.__new__(agent_module.Agent)
        agent.database_guard = Mock()
        agent.config = {'backup': '/nao-usado', 'backup_sha256': 'a' * 64}
        with patch.object(agent_module.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                agent.restore('b' * 64)
            run.assert_not_called()

    def test_restore_refuses_active_application_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / 'referencia.dump'
            backup.write_bytes(b'backup controlado')
            agent = agent_module.Agent.__new__(agent_module.Agent)
            agent.database_guard = Mock()
            expected = agent_module.digest(backup)
            agent.config = {'backup': str(backup), 'backup_sha256': expected}
            agent.sql = Mock(return_value='1')
            with patch.object(agent_module.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    agent.restore(expected)
                run.assert_not_called()

    def test_cache_clear_refuses_unrelated_keys(self):
        agent = agent_module.Agent.__new__(agent_module.Agent)
        agent.redis_command = Mock(return_value='outro-sistema:pedido')
        with self.assertRaises(ValueError):
            agent.clear()
        agent.redis_command.assert_called_once_with('--scan')

    def test_mode_refuses_different_image(self):
        agent = agent_module.Agent.__new__(agent_module.Agent)
        agent.role = 'app'
        with patch.object(agent_module, 'execute', return_value='sha256:outra') as execute:
            with self.assertRaises(ValueError):
                agent.mode('on')
            execute.assert_called_once()

    def test_database_guard_checks_fixed_target(self):
        agent = agent_module.Agent.__new__(agent_module.Agent)
        agent.sql = Mock(return_value=agent_module.DATABASE_MARKER)
        agent.database_guard()
        self.assertIn("datname='tcc_experimento'", agent.sql.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
