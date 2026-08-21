import sys
import unittest
from unittest import mock

from any_karaoke.processes import is_running, launch_module


class TestLaunchModule(unittest.TestCase):
    def test_runs_the_module_with_the_current_interpreter(self):
        with mock.patch("any_karaoke.processes.subprocess.Popen") as popen:
            launch_module("any_karaoke.manager")
        popen.assert_called_once_with([sys.executable, "-m", "any_karaoke.manager"])

    def test_passes_arguments_as_strings(self):
        with mock.patch("any_karaoke.processes.subprocess.Popen") as popen:
            launch_module("any_karaoke.main", r"D:\songs\Song Title")
        popen.assert_called_once_with([sys.executable, "-m", "any_karaoke.main", r"D:\songs\Song Title"])

    def test_returns_the_handle(self):
        with mock.patch("any_karaoke.processes.subprocess.Popen", return_value="handle"):
            self.assertEqual(launch_module("any_karaoke.manager"), "handle")


class TestIsRunning(unittest.TestCase):
    def test_none_is_not_running(self):
        self.assertFalse(is_running(None))

    def test_live_process_is_running(self):
        self.assertTrue(is_running(mock.Mock(poll=lambda: None)))

    def test_exited_process_is_not_running(self):
        self.assertFalse(is_running(mock.Mock(poll=lambda: 0)))

    def test_crashed_process_is_not_running(self):
        self.assertFalse(is_running(mock.Mock(poll=lambda: 1)))


class TestRealRoundTrip(unittest.TestCase):
    def test_the_manager_module_is_actually_launchable(self):
        """Guards against the module path in main.py drifting from the real module."""
        import importlib

        module = importlib.import_module("any_karaoke.manager")
        self.assertTrue(callable(module.main))

    def test_the_player_module_is_actually_launchable(self):
        import importlib

        module = importlib.import_module("any_karaoke.main")
        self.assertTrue(callable(module.main))


if __name__ == "__main__":
    unittest.main()
