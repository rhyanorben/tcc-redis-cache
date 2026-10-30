import importlib.util
import threading
import signal
import tempfile
from unittest.mock import Mock
import unittest
from pathlib import Path
from unittest.mock import patch


source = Path(__file__).resolve().parents[1] / 'manual_session.py'
specification = importlib.util.spec_from_file_location('manual_session', source)
session_module = importlib.util.module_from_spec(specification)
specification.loader.exec_module(session_module)


class ManualSessionTest(unittest.TestCase):
    def test_hangup_closes_manual_sessions_and_removes_socket(self):
        previous = {value: signal.getsignal(value) for value in (signal.SIGHUP, signal.SIGTERM)}
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                socket = root / 'session.sock'
                server = Mock()
                server.handle_request.side_effect = lambda: signal.raise_signal(signal.SIGHUP)
                def create_server(*arguments):
                    socket.touch()
                    return server
                with patch.object(session_module, 'ROOT', root), patch.object(session_module, 'SOCKET', socket), \
                        patch.object(session_module.os, 'getuid', return_value=0), \
                        patch.object(session_module.getpass, 'getpass', return_value='manual-value'), \
                        patch.object(session_module, 'Session') as session, \
                        patch.object(session_module.socketserver, 'ThreadingUnixStreamServer', side_effect=create_server), \
                        patch('sys.argv', ['manual_session.py']):
                    session_module.main()
                    self.assertEqual(3, session.return_value.close.call_count)
                    self.assertFalse(socket.exists())
                    server.server_close.assert_called_once()
        finally:
            for value, handler in previous.items():
                signal.signal(value, handler)

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
