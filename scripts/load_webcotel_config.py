#!/usr/bin/env python3
"""Load RDGen's saved form JSON directly into the existing Windows workflow.

No RDGen backend, ZIP decryptor, token or external configuration endpoint needed.
The mapping intentionally mirrors rdgenerator/views.py (RDGen master, Oct 2026).
"""
import argparse
import base64
import json
import os
import re
from pathlib import Path


def enabled(value):
    return value is True or str(value).strip().lower() in {"true", "on", "yes", "y", "1"}


def yn(value):
    return 'Y' if enabled(value) else 'N'


def make_custom(c):
    direction = c.get('direction', 'both')
    out = {'override-settings': {}, 'default-settings': {}}
    if direction != 'Both':
        out['conn-type'] = direction
    if c.get('installation') == 'installationN':
        out['disable-installation'] = 'Y'
    if c.get('settings') == 'settingsN':
        out['disable-settings'] = 'Y'
    if c.get('appname', '').lower() != 'rustdesk':
        out['app-name'] = c['appname']
    if c.get('permanentPassword'):
        raise ValueError('A fixed password is intentionally not supported in this customer support build')

    theme = c.get('theme', 'system')
    if theme != 'system':
        group = 'override-settings' if c.get('themeDorO') == 'override' else 'default-settings'
        out[group]['theme'] = theme
    out['enable-lan-discovery'] = 'N' if enabled(c.get('denyLan')) else 'Y'
    out['allow-auto-disconnect'] = yn(c.get('autoClose', False))

    group = 'default-settings' if c.get('permissionsDorO', 'default') == 'default' else 'override-settings'
    perms = out[group]
    perms['access-mode'] = c.get('permissionsType', 'custom')
    for key, setting in {
        'enableKeyboard': 'enable-keyboard',
        'enableClipboard': 'enable-clipboard',
        'enableFileTransfer': 'enable-file-transfer',
        'enableAudio': 'enable-audio',
        'enableTCP': 'enable-tunnel',
        'enableRemoteRestart': 'enable-remote-restart',
        'enableRecording': 'enable-record-session',
        'enableBlockingInput': 'enable-block-input',
        'enableRemoteModi': 'allow-remote-config-modification',
        'enableDirectIP': 'direct-server',
        'hidecm': 'allow-hide-cm',
        'removeWallpaper': 'allow-remove-wallpaper',
        'enablePrinter': 'enable-remote-printer',
        'enableCamera': 'enable-camera',
        'enableTerminal': 'enable-terminal',
    }.items():
        perms[setting] = yn(c.get(key, False))
    perms['verification-method'] = 'use-permanent-password' if enabled(c.get('hidecm')) else 'use-both-passwords'
    perms['approve-mode'] = c.get('passApproveMode', 'password-click')
    if group == 'override-settings' and direction == 'incoming':
        perms['custom-rendezvous-server'] = c['serverIP']
        perms['api-server'] = c.get('apiServer') or c['serverIP'] + ':21114'

    for field, dest in [('defaultManual', 'default-settings'), ('overrideManual', 'override-settings')]:
        for line in c.get(field, '').splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                out[dest][k.strip()] = v.strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--assets', required=True)
    ap.add_argument('--check-only', action='store_true')
    args = ap.parse_args()
    c = json.loads(Path(args.config).read_text(encoding='utf-8'))
    root = Path(args.assets)
    for name in ['icon.png', 'logo.png', 'privacy.png']:
        file = root / name
        if not file.is_file() or not file.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
            raise RuntimeError(f'Missing or invalid PNG: {file}')

    if c.get('platform') != 'windows' or c.get('version') != '1.5.0':
        raise RuntimeError('This workflow is explicitly pinned to Windows / RustDesk 1.5.0')
    if c.get('direction') != 'incoming':
        raise RuntimeError('Expected an incoming-only support client')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', c.get('exename', '')):
        raise RuntimeError('Unsafe executable name')
    if not re.fullmatch(r'[\w .-]+', c.get('appname', ''), re.ASCII):
        raise RuntimeError('Invalid application name')
    if not re.fullmatch(r'[a-zA-Z0-9.-]+', c.get('serverIP', '')):
        raise RuntimeError('Invalid ID server name')
    if not str(c.get('serverPort', '')).isdigit():
        raise RuntimeError('Invalid port')
    if not c.get('key', '').strip():
        raise RuntimeError('Public RustDesk server key must not be empty')

    custom = make_custom(c)
    custom_encoded = base64.b64encode(json.dumps(custom, ensure_ascii=True, separators=(',', ':')).encode('ascii')).decode('ascii')
    values = {
        'server': c['serverIP'],
        'serverPort': str(c['serverPort']),
        'key': c['key'],
        'apiServer': c.get('apiServer') or c['serverIP']+':21114',
        'custom': custom_encoded,
        'iconlink_url': 'true',
        'logolink_url': 'true',
        'appname': c['appname'],
        'urlLink': c.get('urlLink') or 'https://rustdesk.com',
        'downloadLink': c.get('downloadLink') or 'https://rustdesk.com/download',
        'delayFix': 'true' if enabled(c.get('delayFix')) else 'false',
        'xOffline': 'true' if enabled(c.get('xOffline')) else 'false',
        'removeNewVersionNotif': 'true' if enabled(c.get('removeNewVersionNotif')) else 'false',
        'compname': c.get('compname') or 'Purslane Ltd',
        'filename': c['exename'],
    }
    print('webcotel Support configuration:')
    print('  application:', c['appname'])
    print('  executable:', c['exename']+'.exe')
    print('  ID server:', c['serverIP']+':'+str(c['serverPort']))
    print('  mode:', c['direction'])
    print('  branding: icon, logo, privacy PNG validated')
    if not args.check_only:
        env = Path(os.environ['GITHUB_ENV'])
        with env.open('a', encoding='utf-8') as f:
            for k, v in values.items():
                v = str(v)
                if '\n' in v or '\r' in v:
                    raise ValueError(f'Unexpected newline in {k}')
                f.write(f'{k}={v}\n')
        print('GitHub build variables prepared.')
    else:
        print('Local validation successful.')


if __name__ == '__main__':
    main()
