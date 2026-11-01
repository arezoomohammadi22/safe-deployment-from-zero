"""Local-only, validated NGINX traffic switch. No Docker socket inside containers."""
import subprocess
from pathlib import Path

PROFILES = ('95-5','80-20','100-0','0-100')
ROOT = Path(__file__).resolve().parents[1]


def current_profile(root: Path = ROOT) -> str:
    active = (root / 'nginx/active.conf').read_text()
    for p in PROFILES:
        if active == (root / f'nginx/{p}.conf').read_text():
            return p
    return 'custom'


def compose_cmd(root: Path = ROOT) -> list[str]:
    return ['docker', 'compose', '--project-directory', str(root),
            '-f', str(root / 'compose.yml'), '-p', 'safe-observe']


def set_profile(profile: str, root: Path = ROOT, execute: bool = False) -> bool:
    """Return True only when a valid config has been activated via NGINX reload.

    The bind mounted config file must be rewritten IN PLACE, not os.replace()'d.
    """
    if profile not in PROFILES:
        raise ValueError(f'Unknown profile: {profile}')
    active_file = root / 'nginx/active.conf'
    new_config = (root / f'nginx/{profile}.conf').read_text()
    old_config = active_file.read_text()
    if old_config == new_config:
        print(f'Already using {profile}; no action necessary')
        return False
    if not execute:
        print(f'DRY RUN: would change traffic {current_profile(root)} -> {profile}')
        return False
    # No public endpoint or privileged container required. Needs local docker CLI access.
    command = compose_cmd(root) + ['exec','-T','nginx','nginx']
    with active_file.open('w', encoding='utf-8') as output:
        output.write(new_config)
    try:
        subprocess.run(command + ['-t'], check=True, timeout=15)
        subprocess.run(command + ['-s','reload'], check=True, timeout=15)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as error:
        with active_file.open('w', encoding='utf-8') as output:
            output.write(old_config)
        try:
            subprocess.run(command + ['-t'], check=True, timeout=15)
            subprocess.run(command + ['-s','reload'], check=True, timeout=15)
        except Exception as restore_error:
            print(f'CRITICAL: unable to reload old NGINX config: {restore_error}')
        raise RuntimeError(f'Failed to activate {profile}; original config restored on disk') from error
    print(f'NGINX traffic profile switched to {profile}')
    return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Safely switch local NGINX canary routing')
    parser.add_argument('profile', choices=PROFILES)
    parser.add_argument('--execute', action='store_true', help='Apply config + validate + reload; default is dry-run')
    args = parser.parse_args()
    set_profile(args.profile, execute=args.execute)
