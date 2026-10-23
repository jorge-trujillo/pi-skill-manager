"""Automation interface; all mutations delegate to the shared Manager."""
import argparse
import sys
from .core import Manager, ManagerError

WARNING = 'Review the source before installing. Skills are untrusted instructions; linking is not compatibility conversion. Claude tools and dependencies are not installed. Use /reload in Pi.'


def skill_card(skill, installed, *, source=False):
    lines = [f'{skill.name} [{"installed" if installed else "available"}]',
             f'  Identity: {skill.identity}']
    description = str(skill.description).splitlines() or ['']
    lines.append('  Description: ' + description[0])
    lines.extend('    ' + line for line in description[1:])
    if source:
        lines.append(f'  Source: {skill.path}')
    return '\n'.join(lines)


def installed_card(entry):
    status = 'managed' if entry.managed else 'unmanaged'
    if entry.broken:
        status += ', broken'
    lines = [f'{entry.name} [{status}]']
    if entry.target is not None:
        lines.append(f'  Target: {entry.target}')
    lines.append(f'  Path: {entry.path}')
    return '\n'.join(lines)


def parser():
    p = argparse.ArgumentParser(description='Import marketplace skills into Pi')
    p.add_argument('--agent-dir', help='Agent directory (place before subcommands)')
    groups = p.add_subparsers(dest='group')
    marketplaces = groups.add_parser('marketplace').add_subparsers(dest='operation', required=True)
    add = marketplaces.add_parser('add')
    add.add_argument('url')
    add.add_argument('--name')
    marketplaces.add_parser('list')
    marketplaces.add_parser('update').add_argument('identity')
    skills = groups.add_parser('skills').add_subparsers(dest='operation', required=True)
    skills.add_parser('list').add_argument('identity', nargs='?')
    for command in ('install', 'install-plugin', 'remove'):
        skills.add_parser(command).add_argument('identity')
    skills.add_parser('installed')
    return p


def main(argv=None, *, manager_factory=Manager):
    args = parser().parse_args(argv)
    manager = manager_factory(args.agent_dir)
    try:
        if args.group is None:
            from .tui import run
            run(manager)
        elif args.group == 'marketplace':
            if args.operation == 'add':
                print('Added:', manager.add(args.url, args.name))
            elif args.operation == 'list':
                for name, display, error in manager.marketplaces():
                    print(f'{name}: {error or display}')
            else:
                issues = manager.update(args.identity)
                print('Updated. Existing links expose new content.')
                for issue in issues:
                    print('Warning:', issue)
        elif args.operation == 'list':
            skills, issues = manager.discover(args.identity)
            entries = {e.target for e in manager.installed() if e.managed}
            for skill in skills:
                print(skill_card(skill, skill.path in entries, source=True) + '\n')
            for issue in issues:
                print('Warning:', issue)
        elif args.operation == 'installed':
            for entry in manager.installed():
                print(installed_card(entry) + '\n')
        elif args.operation == 'remove':
            manager.remove(args.identity)
            print('Removed link:', args.identity)
        else:
            proposed = manager.select(args.identity, plugin=args.operation == 'install-plugin')
            print(WARNING)
            for skill in proposed:
                print('Source:', skill.path)
            created = manager.install_plugin(args.identity) if args.operation == 'install-plugin' else manager.install(args.identity)
            print('Installed: ' + ', '.join(created) if created else 'Already installed; no changes.')
        return 0
    except (ManagerError, OSError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Cancelled.', file=sys.stderr)
        return 130
