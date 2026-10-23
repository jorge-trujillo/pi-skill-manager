import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_manager.core import Manager, ManagerError


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], stderr=subprocess.STDOUT, text=True)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'origin'
        self.repo.mkdir()
        git(self.repo, 'init')
        git(self.repo, 'config', 'user.email', 'test@example.test')
        git(self.repo, 'config', 'user.name', 'Test')
        (self.repo / '.claude-plugin').mkdir()
        (self.repo / '.claude-plugin/marketplace.json').write_text(json.dumps({'name': 'Display', 'plugins': [{'name': 'plug', 'source': './plug'}]}))
        self.make_skill('a', 'alpha')
        self.make_skill('b', 'beta')
        self.commit()
        self.m = Manager(self.root / 'agent')
        self.m.add(str(self.repo), name='market', allow_local=True)

    def make_skill(self, directory, name):
        p = self.repo / 'plug/skills' / directory
        p.mkdir(parents=True, exist_ok=True)
        (p / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: "A: useful skill"\n---\nInstructions\n')
        (p / 'support.txt').write_text('support')

    def commit(self):
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'fixture')

    def test_discovery_install_remove(self):
        skills, issues = self.m.discover('market')
        self.assertEqual(issues, [])
        self.assertEqual(skills[0].description, 'A: useful skill')
        self.m.install('market/plug/a')
        self.assertEqual((self.m.skills_dir / 'alpha/support.txt').read_text(), 'support')
        self.assertTrue((self.m.skills_dir / 'alpha').readlink().is_absolute())
        self.assertEqual(self.m.install('market/plug/a'), [])
        self.assertTrue(self.m.installed()[0].managed)
        self.m.remove('alpha')
        self.assertTrue(skills[0].path.exists())

    def test_unmanaged_and_collision(self):
        p = self.m.skills_dir / 'custom/nested'
        p.mkdir(parents=True)
        (p / 'SKILL.md').write_text('---\nname: alpha\ndescription: custom\n---\n')
        with self.assertRaises(ManagerError):
            self.m.install_plugin('market/plug')
        self.assertFalse((self.m.skills_dir / 'beta').exists())
        with self.assertRaises(ManagerError):
            self.m.remove('custom')
        (self.m.skills_dir / 'beta').symlink_to('/nonexistent')
        with self.assertRaises(ManagerError):
            self.m.install('market/plug/b')

    def test_rollback(self):
        original = Path.symlink_to
        calls = []
        def fail(path, target, **kwargs):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('simulated')
            original(path, target, **kwargs)
        with patch.object(Path, 'symlink_to', fail):
            with self.assertRaises(ManagerError):
                self.m.install_plugin('market/plug')
        self.assertEqual(list(self.m.skills_dir.iterdir()), [])

    def test_update_broken_dirty_diverged(self):
        self.m.install('market/plug/a')
        import shutil
        shutil.rmtree(self.repo / 'plug/skills/a')
        self.commit()
        self.assertTrue(any('broken' in x for x in self.m.update('market')))
        self.assertTrue(self.m.installed()[0].managed)
        self.assertTrue(self.m.installed()[0].broken)
        checkout = self.m.marketplaces_dir / 'market'
        (checkout / 'dirty').write_text('x')
        with self.assertRaisesRegex(ManagerError, 'dirty'):
            self.m.update('market')
        (checkout / 'dirty').unlink()
        git(checkout, 'config', 'user.email', 'test@example.test')
        git(checkout, 'config', 'user.name', 'Test')
        (checkout / 'local').write_text('x')
        git(checkout, 'add', '.')
        git(checkout, 'commit', '-m', 'local')
        (self.repo / 'remote').write_text('x')
        self.commit()
        with self.assertRaises(ManagerError):
            self.m.update('market')

    def test_invalid_and_containment(self):
        with self.assertRaises(ManagerError):
            self.m.add(str(self.repo))
        with self.assertRaises(ManagerError):
            self.m.add('https://example.test/x.git', name='../bad')
        manifest = self.m.marketplaces_dir / 'market/.claude-plugin/marketplace.json'
        manifest.write_text(json.dumps({'name': 'x', 'plugins': [{'name': 'bad', 'source': '../escape'}]}))
        with self.assertRaises(ManagerError):
            self.m.discover('market')

    def test_invalid_skill_and_external(self):
        checkout = self.m.marketplaces_dir / 'market'
        (checkout / 'plug/skills/a/SKILL.md').write_text('---\nname: [broken\n---\n')
        manifest = checkout / '.claude-plugin/marketplace.json'
        data = json.loads(manifest.read_text())
        data['plugins'].append({'name': 'external', 'source': {'source': 'github', 'repo': 'x/y'}})
        manifest.write_text(json.dumps(data))
        skills, issues = self.m.discover('market')
        self.assertEqual(len(skills), 1)
        self.assertEqual(len(issues), 2)

    def test_escaping_skill_and_managed_link(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'SKILL.md').write_text('---\nname: escape\ndescription: no\n---\n')
        base = self.m.marketplaces_dir / 'market/plug/skills'
        (base / 'escape').symlink_to(outside, target_is_directory=True)
        # A directly linked SKILL.md must also be rejected by containment.
        (base / 'a/SKILL.md').unlink()
        (base / 'a/SKILL.md').symlink_to(outside / 'SKILL.md')
        skills, issues = self.m.discover('market')
        self.assertTrue(any('escapes' in issue for issue in issues))
        self.assertFalse(any(s.name == 'escape' for s in skills))
        self.m.skills_dir.mkdir()
        (self.m.skills_dir / 'unmanaged').symlink_to(outside)
        self.assertFalse(self.m.installed()[0].managed)
        with self.assertRaises(ManagerError):
            self.m.remove('unmanaged')
        self.assertTrue(outside.exists())

    def test_update_reports_new_collision(self):
        self.m.install_plugin('market/plug')
        self.make_skill('b', 'alpha')
        self.commit()
        issues = self.m.update('market')
        self.assertTrue(any('collision' in issue for issue in issues))
        self.assertTrue((self.m.skills_dir / 'beta').is_symlink())

    def test_plugin_internal_collision(self):
        (self.m.marketplaces_dir / 'market/plug/skills/b/SKILL.md').write_text('---\nname: alpha\ndescription: duplicate\n---\n')
        with self.assertRaises(ManagerError):
            self.m.install_plugin('market/plug')
        self.assertFalse(self.m.skills_dir.exists())


if __name__ == '__main__':
    unittest.main()
