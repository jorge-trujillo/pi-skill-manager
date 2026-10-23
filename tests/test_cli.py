import contextlib
import io
from .test_core import CoreTests
from skill_manager.cli import main, skill_card, installed_card
from types import SimpleNamespace
from skill_manager.core import Manager


class CLITests(CoreTests):
    def invoke(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(['--agent-dir', str(self.m.agent_dir), *args], manager_factory=self.factory)
        self.assertEqual(code, 0, output.getvalue())
        return output.getvalue()

    def factory(self, agent):
        manager = Manager(agent)
        original = manager.add
        manager.add = lambda url, name=None: original(url, name, allow_local=True)
        return manager

    def test_cli_lifecycle(self):
        self.invoke('marketplace', 'add', str(self.repo), '--name', 'second')
        self.assertIn('Display', self.invoke('marketplace', 'list'))
        self.assertIn('market/plug/a', self.invoke('skills', 'list', 'market'))
        self.invoke('skills', 'install', 'market/plug/a')
        self.invoke('skills', 'install-plugin', 'market/plug')
        self.assertIn('managed', self.invoke('skills', 'installed'))
        self.invoke('skills', 'remove', 'alpha')
        self.invoke('marketplace', 'update', 'market')

    def test_multiline_skill_cards(self):
        output = self.invoke('skills', 'list', 'market')
        self.assertIn('alpha [available]\n  Identity: market/plug/a\n  Description: A: useful skill\n  Source: ', output)
        self.invoke('skills', 'install', 'market/plug/a')
        self.assertIn('alpha [installed]\n', self.invoke('skills', 'list', 'market'))
        output = self.invoke('skills', 'installed')
        self.assertIn('alpha [managed]\n  Target: ', output)
        self.assertIn('\n  Path: ' + str(self.m.skills_dir / 'alpha'), output)

    def test_card_details_and_statuses(self):
        skill = SimpleNamespace(name='example', identity='market/plugin/example',
                                description='First line\nSecond line', path='/source')
        self.assertEqual(skill_card(skill, False),
                         'example [available]\n  Identity: market/plugin/example\n'
                         '  Description: First line\n    Second line')
        entry = SimpleNamespace(name='example', managed=False, broken=True,
                                target='/missing', path='/skills/example')
        self.assertEqual(installed_card(entry),
                         'example [unmanaged, broken]\n  Target: /missing\n  Path: /skills/example')
        entry.target = None
        self.assertEqual(installed_card(entry),
                         'example [unmanaged, broken]\n  Path: /skills/example')

    def test_public_cli_rejects_local_and_nonterminal(self):
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(['--agent-dir', str(self.m.agent_dir), 'marketplace', 'add', str(self.repo)]), 1)
        self.assertIn('HTTPS or SSH', error.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(['--agent-dir', str(self.m.agent_dir)]), 1)
        self.assertIn('terminal', error.getvalue())
