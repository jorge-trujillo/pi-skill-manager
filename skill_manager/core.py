"""Filesystem-backed skill operations. Repository contents are never executed."""
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml


class ManagerError(Exception):
    """An actionable operation failure."""


def safe_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', value):
        raise ManagerError(f'Invalid name: {value!r}; use letters, digits, dot, dash or underscore.')
    return value


def local_source(source):
    return isinstance(source, str) and not (':' in source or source.startswith('git@'))


def contained(path, root):
    return path.resolve().is_relative_to(root.resolve())


def frontmatter(path):
    try:
        text = path.read_text()
        lines = text.splitlines()
        if not lines or lines[0] != '---':
            raise ValueError('missing YAML frontmatter')
        end = lines.index('---', 1)
        data = yaml.safe_load('\n'.join(lines[1:end]))
        if not isinstance(data, dict):
            raise ValueError('frontmatter must be a mapping')
        name = safe_name(data.get('name'))
        description = data.get('description')
        if not isinstance(description, str) or not description.strip():
            raise ValueError('description must be a nonempty string')
        return name, description
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        raise ManagerError(f'Invalid skill {path}: {exc}') from exc


@dataclass
class Skill:
    identity: str
    name: str
    description: str
    path: Path


@dataclass
class Installed:
    name: str
    path: Path
    target: Path | None
    managed: bool
    broken: bool


class Manager:
    def __init__(self, agent_dir=None):
        self.agent_dir = Path(agent_dir or '~/.pi/agent').expanduser().absolute()
        self.marketplaces_dir = self.agent_dir / 'marketplaces'
        self.skills_dir = self.agent_dir / 'skills'

    def git(self, *args):
        try:
            result = subprocess.run(['git', *map(str, args)], check=False)
        except OSError as exc:
            raise ManagerError(f'Cannot run Git: {exc}') from exc
        if result.returncode:
            raise ManagerError(f'Git failed (exit {result.returncode}); check authentication and the output above.')

    def checkout(self, name):
        path = self.marketplaces_dir / safe_name(name)
        if path.is_symlink() or not path.is_dir():
            raise ManagerError(f'No managed checkout: {name}')
        self.manifest(path)
        return path

    def manifest(self, root):
        file = root / '.claude-plugin/marketplace.json'
        if not contained(file, root):
            raise ManagerError('Manifest escapes checkout')
        try:
            data = json.loads(file.read_text())
        except (OSError, UnicodeError, ValueError) as exc:
            raise ManagerError(f'Invalid marketplace manifest at {file}: {exc}') from exc
        if not isinstance(data, dict) or not isinstance(data.get('name'), str) or not data['name'] or not isinstance(data.get('plugins'), list):
            raise ManagerError('Manifest requires name and plugins array')
        seen = set()
        for plugin in data['plugins']:
            if not isinstance(plugin, dict):
                raise ManagerError('Plugin must be an object')
            name = safe_name(plugin.get('name'))
            if name in seen:
                raise ManagerError(f'Ambiguous plugin identifier: {name}')
            seen.add(name)
            source = plugin.get('source')
            if local_source(source):
                if Path(source).is_absolute() or not contained(root / source, root):
                    raise ManagerError(f'Plugin path escapes checkout: {source}')
            elif source is None:
                raise ManagerError(f'Plugin {name} is missing source')
        return data

    def add(self, url, name=None, *, allow_local=False):
        # allow_local is a Python-only fixture seam, never exposed by the CLI.
        parsed = urlparse(url)
        valid = ((parsed.scheme in ('https', 'ssh') and bool(parsed.hostname) and bool(parsed.path.strip('/')))
                 or bool(re.fullmatch(r'[^\s/@:]+@[^\s/:]+:[^\s]+', url)))
        if not valid and not (allow_local and Path(url).is_dir()):
            raise ManagerError('Use an HTTPS or SSH Git URL (not a local path).')
        basename = url.rstrip('/').split('/')[-1].split(':')[-1]
        derived = re.sub(r'[^A-Za-z0-9._-]', '-', basename.removesuffix('.git')).strip('.-')
        name = safe_name(name if name is not None else derived)
        self.marketplaces_dir.mkdir(parents=True, exist_ok=True)
        destination = self.marketplaces_dir / name
        if os.path.lexists(destination):
            raise ManagerError(f'Destination occupied: {destination}; select another ID with --name.')
        temporary = Path(tempfile.mkdtemp(prefix='.clone-', dir=self.marketplaces_dir))
        try:
            self.git('clone', '--', url, temporary)
            self.manifest(temporary)
            self.discover_root(temporary, name)
            if os.path.lexists(destination):
                raise ManagerError(f'Destination became occupied: {destination}')
            temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return name

    def marketplaces(self):
        entries = []
        if self.marketplaces_dir.exists():
            for path in sorted(self.marketplaces_dir.iterdir()):
                if path.name.startswith('.'):
                    continue
                try:
                    root = self.checkout(path.name)
                    entries.append((path.name, self.manifest(root)['name'], None))
                except ManagerError as exc:
                    entries.append((path.name, '', str(exc)))
        return entries

    def discover_root(self, root, marketplace):
        skills, issues = [], []
        for plugin in self.manifest(root)['plugins']:
            name, source = plugin['name'], plugin['source']
            if not local_source(source):
                issues.append(f'{marketplace}/{name}: unsupported external source {source!r}')
                continue
            base = root / source / 'skills'
            if not contained(base, root):
                raise ManagerError(f'Skills path escapes checkout: {base}')
            if not (root / source).is_dir():
                issues.append(f'{marketplace}/{name}: local plugin source does not exist: {source}')
                continue
            for file in sorted(base.rglob('SKILL.md')):
                identity = f'{marketplace}/{name}/{file.parent.relative_to(base).as_posix()}'
                try:
                    if not contained(file, root):
                        raise ManagerError(f'Skill path escapes checkout: {file}')
                    declared, description = frontmatter(file)
                    skills.append(Skill(identity, declared, description, file.parent.resolve()))
                except ManagerError as exc:
                    issues.append(f'{identity}: {exc}')
        return skills, issues

    def discover(self, marketplace=None):
        if marketplace:
            return self.discover_root(self.checkout(marketplace), marketplace)
        skills, issues = [], []
        for name, _, error in self.marketplaces():
            if error:
                issues.append(error)
                continue
            found, invalid = self.discover(name)
            skills.extend(found)
            issues.extend(invalid)
        return skills, issues

    def installed(self):
        roots = [self.checkout(name).resolve() for name, _, error in self.marketplaces() if not error]
        entries = []
        if self.skills_dir.exists():
            for path in sorted(self.skills_dir.iterdir()):
                target = Path(os.path.abspath(path.parent / os.readlink(path))) if path.is_symlink() else None
                # Lexical ownership keeps broken links identifiable; resolution prevents escaping links.
                managed = target is not None and any(target.is_relative_to(root) and contained(target, root) for root in roots)
                entries.append(Installed(path.name, path, target, managed, path.is_symlink() and not path.exists()))
        return entries

    def existing_names(self):
        names = {}
        if self.skills_dir.exists():
            files = set(self.skills_dir.rglob('SKILL.md'))
            for entry in self.skills_dir.iterdir():
                if entry.is_dir():
                    files.update(entry.rglob('SKILL.md'))
            for file in files:
                try:
                    name, _ = frontmatter(file)
                    names.setdefault(name, set()).add(file.parent.resolve())
                except ManagerError:
                    pass
        return names

    def select(self, identity, plugin=False):
        skills, issues = self.discover()
        found = [s for s in skills if s.identity.startswith(identity + '/')] if plugin else [s for s in skills if s.identity == identity]
        if plugin and len(identity.split('/')) != 2:
            raise ManagerError('Plugin identity must be marketplace/plugin')
        if plugin and any(x.startswith(identity + '/') or x.startswith(identity + ':') for x in issues):
            raise ManagerError('Plugin contains invalid or unsupported entries: ' + '; '.join(issues))
        if not found:
            raise ManagerError(f'No installable skills for {identity}')
        if not plugin and len(found) != 1:
            raise ManagerError(f'Ambiguous identifier: {identity}')
        return found

    def install_many(self, proposed):
        existing = self.existing_names()
        managed = {e.name: e for e in self.installed()}
        names, pending = set(), []
        for skill in proposed:
            if skill.name in names:
                raise ManagerError(f'Plugin declares duplicate name: {skill.name}')
            names.add(skill.name)
            destination = self.skills_dir / skill.name
            entry = managed.get(skill.name)
            identical = entry and entry.managed and entry.target == skill.path
            if os.path.lexists(destination) and not identical:
                raise ManagerError(f'Destination occupied: {destination}')
            if existing.get(skill.name, set()) - ({skill.path} if identical else set()):
                raise ManagerError(f'Declared-name collision: {skill.name}')
            if not identical:
                pending.append((destination, skill.path))
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        created = []
        try:
            for destination, source in pending:
                destination.symlink_to(source, target_is_directory=True)
                created.append(destination)
        except OSError as exc:
            for destination in reversed(created):
                destination.unlink()
            raise ManagerError(f'Installation failed; created links rolled back: {exc}') from exc
        return [p.name for p in created]

    def install(self, identity):
        return self.install_many(self.select(identity))

    def install_plugin(self, identity):
        return self.install_many(self.select(identity, plugin=True))

    def remove(self, name):
        safe_name(name)
        entry = next((e for e in self.installed() if e.name == name), None)
        if not entry or not entry.managed:
            raise ManagerError(f'Refusing removal of unmanaged entry: {name}')
        entry.path.unlink()

    def update(self, name):
        root = self.checkout(name)
        try:
            status = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], text=True, stderr=subprocess.STDOUT)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ManagerError(f'Cannot inspect checkout: {exc}') from exc
        if status:
            raise ManagerError('Checkout is dirty; commit or remove changes before updating.')
        self.git('-C', root, 'pull', '--ff-only')
        available, issues = self.discover()
        declared = {}
        for skill in available:
            declared.setdefault(skill.name, set()).add(skill.path)
        issues.extend(f'discoverable declared-name collision: {n}' for n, paths in declared.items() if len(paths) > 1)
        issues.extend(f'broken installed target: {e.name} -> {e.target}' for e in self.installed() if e.broken)
        issues.extend(f'declared-name collision: {n}' for n, paths in self.existing_names().items() if len(paths) > 1)
        return issues
