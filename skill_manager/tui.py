"""Small scrolling curses menus with a terminal handoff for Git authentication."""
import curses
import sys
import termios
import textwrap
from .core import ManagerError
from .cli import skill_card, installed_card


class UI:
    def __init__(self, screen, manager):
        self.screen, self.manager = screen, manager
        screen.keypad(True)
        curses.set_escdelay(100)
        try:
            curses.curs_set(0)
        except curses.error:
            pass

    def draw(self, y, text):
        height, width = self.screen.getmaxyx()
        if y < height - 1 and width > 1:
            try:
                self.screen.addnstr(y, 0, str(text).replace('\n', ' ').replace('\r', ' '), width - 1)
            except curses.error:
                pass

    def menu(self, title, options):
        selected = 0
        start = 0
        while True:
            self.screen.erase()
            height, width = self.screen.getmaxyx()
            capacity = max(0, height - 4)
            # Reserve the marker on every physical line, including continuations.
            wrapped = [
                [part for line in str(option).splitlines() or ['']
                 for part in textwrap.wrap(line, max(1, width - 3),
                                           replace_whitespace=True) or ['']]
                for option in options
            ]
            start = min(start, selected)
            # Scroll by entries, keeping the selected card fully visible when
            # possible. An oversized card starts at the top and is clipped.
            while start < selected and sum(len(lines) for lines in wrapped[start:selected + 1]) > capacity:
                start += 1
            self.draw(0, title)
            self.draw(1, '↑/↓ move · Enter select · Esc/q back/quit')
            row = 3
            for index in range(start, len(wrapped)):
                for offset, line in enumerate(wrapped[index]):
                    if row >= 3 + capacity:
                        break
                    marker = '> ' if index == selected and offset == 0 else '  '
                    self.draw(row, marker + line)
                    row += 1
                if row >= 3 + capacity:
                    break
            self.screen.refresh()
            key = self.screen.getch()
            if key in (27, ord('q')):
                return None
            if key in (curses.KEY_UP, ord('k')):
                selected = max(0, selected - 1)
            elif key in (curses.KEY_DOWN, ord('j')):
                selected = min(max(0, len(options) - 1), selected + 1)
            elif key in (10, 13, curses.KEY_ENTER) and options:
                return selected

    def message(self, text):
        self.menu('Result (Esc/q to return)', str(text).splitlines() or ['No changes'])

    def prompt(self, title):
        value = ''
        while True:
            self.screen.erase()
            self.draw(0, title + ' (Esc cancels)')
            self.draw(2, value)
            self.screen.refresh()
            key = self.screen.get_wch()
            if key == '\x1b':
                return None
            if key in ('\n', '\r'):
                return value
            if key in (curses.KEY_BACKSPACE, '\x7f', '\b'):
                value = value[:-1]
            elif isinstance(key, str) and key.isprintable():
                value += key

    def git_operation(self, operation):
        curses.def_prog_mode()
        curses.endwin()
        try:
            return operation()
        finally:
            curses.reset_prog_mode()
            self.screen.clear()
            self.screen.refresh()

    def install(self, identity, plugin=False):
        created = self.manager.install_plugin(identity) if plugin else self.manager.install(identity)
        self.message('Installed: ' + ', '.join(created) if created else 'Already installed')

    def browse(self):
        while True:
            markets = self.manager.marketplaces()
            choice = self.menu('Marketplaces', [f'{n}: {error or display}' for n, display, error in markets])
            if choice is None:
                return
            name = markets[choice][0]
            root = self.manager.checkout(name)
            plugins = self.manager.manifest(root)['plugins']
            while True:
                choice = self.menu(name + ' / plugins', [p['name'] for p in plugins])
                if choice is None:
                    break
                identity = name + '/' + plugins[choice]['name']
                while True:
                    skills, issues = self.manager.discover(name)
                    skills = [s for s in skills if s.identity.startswith(identity + '/')]
                    installed = {e.target for e in self.manager.installed() if e.managed}
                    options = ['Install all skills'] + [skill_card(s, s.path in installed) for s in skills]
                    choice = self.menu(identity + ' — ' + '; '.join(issues), options)
                    if choice is None:
                        break
                    self.install(identity if choice == 0 else skills[choice - 1].identity, plugin=choice == 0)

    def installed(self):
        while True:
            entries = self.manager.installed()
            choice = self.menu('Installed skills (only managed links may be removed)', [installed_card(e) for e in entries])
            if choice is None:
                return
            entry = entries[choice]
            if not entry.managed:
                self.message('Unmanaged entries cannot be removed.')
            elif self.menu('Remove link ' + entry.name + '? Source is preserved.', ['Cancel', 'Remove']) == 1:
                self.manager.remove(entry.name)
                self.message('Removed ' + entry.name)

    def run(self):
        while True:
            choice = self.menu('Pi Skill Marketplace Manager', ['Add marketplace', 'List marketplaces', 'Browse/install skills', 'Installed skills', 'Update marketplace', 'Quit'])
            try:
                if choice is None or choice == 5:
                    return
                if choice == 0:
                    url = self.prompt('Git SSH/HTTPS URL')
                    if url:
                        name = self.prompt('Optional marketplace ID (empty derives from repository)')
                        if name is not None:
                            result = self.git_operation(lambda: self.manager.add(url, name or None))
                            self.message('Added ' + result)
                elif choice == 1:
                    self.message('\n'.join(f'{n}: {error or display}' for n, display, error in self.manager.marketplaces()) or 'No marketplaces')
                elif choice == 2:
                    self.browse()
                elif choice == 3:
                    self.installed()
                elif choice == 4:
                    names = [n for n, _, error in self.manager.marketplaces() if not error]
                    selected = self.menu('Update marketplace', names)
                    if selected is not None:
                        issues = self.git_operation(lambda: self.manager.update(names[selected]))
                        self.message('Updated\n' + '\n'.join(issues))
            except (ManagerError, OSError) as exc:
                self.message('Error: ' + str(exc))


def run(manager):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ManagerError('Interactive mode requires a usable terminal; use --help for CLI commands.')
    original = termios.tcgetattr(sys.stdin.fileno())
    try:
        curses.wrapper(lambda screen: UI(screen, manager).run())
    except curses.error as exc:
        raise ManagerError(f'Cannot initialize terminal ({exc}); check TERM or use CLI commands.') from exc
    finally:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, original)
