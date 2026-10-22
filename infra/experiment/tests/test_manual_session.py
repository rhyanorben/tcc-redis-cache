import importlib.util
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


source = Path(__file__).resolve().parents[1] / 'manual_session.py'
specification = importlib.util.spec_from_file_location('manual_session', source)
session_module = importlib.util.module_from_spec(specification)
specification.loader.exec_module(session_module)


class ManualSessionTest(unittest.TestCase):
    def test_disconnected_vm_fails_without_waiting_for_request_timeout(self):
        session = session_module.Session.__new__(session_module.Session)
        session.service = 'postgres'
        session.fd = 10
        session.buffer = b''
        session.lock = threading.Lock()
        with patch.object(session_module.os, 'write'), \
                patch.object(session_module.select, 'select', return_value=([10], [], [])), \
                patch.object(session_module.os, 'read', return_value=b''):
            with self.assertRaises(ConnectionError):
                session.request('verify', [])

    def test_close_allows_remote_cleanup_before_terminating_ssh(self):
        session = session_module.Session.__new__(session_module.Session)
        session.pid = 123
        session.fd = 10
        with patch.object(session_module.os, 'write'), \
                patch.object(session_module.os, 'waitpid', return_value=(123, 0)), \
                patch.object(session_module.os, 'close') as close, \
                patch.object(session_module.os, 'kill') as kill:
            session.close()
            close.assert_called_once_with(10)
            kill.assert_not_called()


if __name__ == '__main__':
    unittest.main()
