#!/usr/bin/env python3
"""Remove RDGen generator-server dependence from the Windows privacy DLL job.

Run from repository root: py -3 scripts/fix_topmost_workflow.py
Modifies only .github/workflows/third-party-RustDeskTempTopMostWindow.yml.
"""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / '.github/workflows/third-party-RustDeskTempTopMostWindow.yml'
MARKER = 'Use local webcotel privacy image'

def main():
    if not TARGET.exists():
        raise SystemExit(f'Workflow file missing: {TARGET}\nExtract patch into your rdgen repository root.')
    src = TARGET.read_text(encoding='utf-8')
    if MARKER in src:
        print('Already patched: no changes needed.')
        return
    pre = re.compile(r'(?ms)^      - uses: actions/download-artifact@v5\s*\n.*?(?=^      - name: Download the source code\s*$)')
    text, n = pre.subn('', src)
    if n != 1:
        raise SystemExit('Old encrypted ZIP step not found exactly once; leaving workflow unchanged.')

    # Fix remote privacy-image URL dependency, reuse existing local PNG in repository
    privacy = re.compile(r'(?ms)^            if \(\$env:privacylink_url-ne "false"\) \{\s*\n.*?^            \}\s*\n(?=            msbuild )')
    replacement = '''            # Use local webcotel privacy image from the fork (no RDGen API)
            $privacy = Join-Path $env:GITHUB_WORKSPACE 'config/assets/privacy.png'
            if (!(Test-Path $privacy)) { throw "Missing webcotel privacy PNG: $privacy" }
            Copy-Item -Path $privacy -Destination './privacy.png' -Force
            python "$env:GITHUB_WORKSPACE/.github/patches/privacyScreen.py"
            if ($LASTEXITCODE -ne 0 -or !(Test-Path './img.cpp')) { throw 'Failed to convert webcotel privacy image' }
            Copy-Item -Path './img.cpp' -Destination './WindowInjection/img.cpp' -Force
'''
    text, n = privacy.subn(lambda _: replacement, text)
    if n != 1:
        raise SystemExit('Old remote privacy URL step not found exactly once; leaving workflow unchanged.')

    text = text.replace('      - name: Build the project\n', f'      # {MARKER}\n      - name: Build the project\n', 1)
    # Increase retry timeout because privacy image is converted to a sizeable C++ source.
    text = text.replace('          timeout_minutes: 5\n', '          timeout_minutes: 12\n', 1)
    for forbidden in ('encrypted-secrets-zip', 'secrets.ZIP_PASSWORD', 'secrets.GENURL', 'privacylink_url', '/cleanzip'):
        if forbidden in text:
            raise SystemExit(f'Unexpected remaining generator dependency: {forbidden}')
    backup = TARGET.with_suffix('.yml.before-webcotel-fix.bak')
    if not backup.exists():
        shutil.copy2(TARGET, backup)
    TARGET.write_text(text, encoding='utf-8')
    print('Patched:', TARGET)
    print('Backup:', backup)
    print('Privacy screen is now compiled from config/assets/privacy.png, no RDGen server required.')

if __name__ == '__main__':
    main()
