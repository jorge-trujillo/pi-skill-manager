import os
import pty
import select
import subprocess
import sys
import tempfile
import termios
import time
import unittest

from .test_core import CoreTests
from skill_manager.tui import UI
import curses
from unittest.mock import patch


class FakeScreen:
    def __init__(self, keys, size=(10, 22)):
        self.keys = iter(keys)
        self.size = size
        self.frames = []

    def keypad(self, enabled):
        pass

    def getmaxyx(self):
        return self.size

    def erase(self):
        self.rows = {}

    def addnstr(self, y, x, text, width):
        self.rows[y] = text[:width]

    def refresh(self):
        self.frames.append(dict(self.rows))

    def getch(self):
        key = next(self.keys)
        if isinstance(key, tuple):
            self.size = key
            return curses.KEY_RESIZE
        return key


class MenuTests(unittest.TestCase):
    def menu(self, screen, options):
        with patch('skill_manager.tui.curses.curs_set'):
            return UI(screen, None).menu('Title', options)

    def test_multiline_wrapping_and_item_selection(self):
        screen = FakeScreen([curses.KEY_DOWN, 10])
        self.assertEqual(self.menu(screen, ['First\nabcdefghijklmnopqrstuvwx', 'Second\ndetail']), 1)
        self.assertEqual(screen.frames[0][3], '> First')
        self.assertEqual(screen.frames[0][4], '  abcdefghijklmnopqrs')
        self.assertEqual(screen.frames[0][5], '  tuvwx')
        self.assertEqual(screen.frames[1][6], '> Second')

    def test_scroll_resize_and_oversized_entry(self):
        screen = FakeScreen([curses.KEY_DOWN, (6, 12), curses.KEY_DOWN, curses.KEY_UP, 10])
        options = ['First\ndetail', 'Long\n' + '\n'.join(['detail'] * 12), 'Last\nend']
        self.assertEqual(self.menu(screen, options), 1)
        self.assertEqual(screen.frames[1][3], '> Long')
        self.assertEqual(screen.frames[2][3], '> Long')
        self.assertEqual(screen.frames[3][3], '> Last')
        self.assertEqual(screen.frames[4][3], '> Long')
        self.assertTrue(all(max(frame) < 5 for frame in screen.frames[2:]))

    def test_empty_and_tiny_menu(self):
        self.assertIsNone(self.menu(FakeScreen([curses.KEY_DOWN, 10, ord('q')], (2, 1)), []))


class TerminalTests(CoreTests):
    @unittest.skipUnless(os.name == 'posix', 'requires POSIX pseudo-terminal')
    def test_menu_navigation_confirmation_resize_and_restoration(self):
        self.m.install('market/plug/a')
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        import fcntl
        import struct
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 8, 100, 0, 0))
        before = termios.tcgetattr(slave)
        child = subprocess.Popen([sys.executable, 'pi_skill_manager.py', '--agent-dir', str(self.m.agent_dir)], stdin=slave, stdout=slave, stderr=slave, env={**os.environ, 'TERM': 'xterm'})
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        output = bytearray()
        def send(keys=b''):
            if keys:
                os.write(master, keys)
            deadline = time.monotonic() + .3
            while time.monotonic() < deadline:
                if select.select([master], [], [], .03)[0]:
                    output.extend(os.read(master, 65536))
        send()
        # Application-mode arrow keys; scroll to installed skills in short viewport.
        send(b'\x1bOB\x1bOB\x1bOB\r')
        send(b'\r')  # select installed link
        send(b'\r')  # cancel removal (default)
        self.assertTrue((self.m.skills_dir / 'alpha').is_symlink())
        send(b'q')  # back to main
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 15, 100, 0, 0))
        import signal
        child.send_signal(signal.SIGWINCH)
        send()
        # Main menu selection restarts at top: update, terminal handoff, result, back.
        send(b'\x1bOB' * 4 + b'\r')
        send(b'\r')
        send(b'q')
        send(b'q')
        child.wait(timeout=5)
        self.assertEqual(child.returncode, 0)
        after = termios.tcgetattr(slave)
        # Python's macOS startup enables IUTF8 before our entry point. Check all
        # interactive mode flags rather than that interpreter-owned flag.
        mask = termios.ECHO | termios.ICANON | termios.ISIG | termios.IEXTEN
        self.assertEqual(after[3] & mask, before[3] & mask)
        self.assertEqual(after[:3] + after[4:], before[:3] + before[4:])
        self.assertIn(b'Remove link alpha?', output)
        self.assertIn(b'Updated', output)
