#!/usr/bin/env python3
"""Converts SunTex091/rdgen's existing Windows generator into a no-server build.
Run from a checkout of that fork after copying this package over its root.
The patcher intentionally fails instead of silently altering unexpected workflow revisions.
"""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / '.github' / 'workflows' / 'generator-windows.yml'


def replace_once(text, pattern, replacement, *, flags=re.MULTILINE | re.DOTALL, desc=''):
    result, count = re.subn(pattern, lambda _: replacement, text, count=1, flags=flags)
    if count != 1:
        raise ValueError(f'Could not locate {desc or pattern}; no modifications saved')
    return result


def main():
    if not TARGET.is_file():
        raise SystemExit('Could not find .github/workflows/generator-windows.yml. Extract this bundle into the RDGen fork root and run there.')
    src = TARGET.read_text(encoding='utf-8')
    if 'GitHub-only webcotel Support' in src:
        print('Already patched. No further changes.')
        return
    if 'name: Custom Windows Client Generator' not in src or 'encrypted-secrets-zip' not in src:
        raise SystemExit('Unexpected workflow version. Stopping to avoid damaging your fork.')
    t = src
    t = replace_once(t, r'\Aname:.*?(?=^env:\s*$)',
        'name: GitHub-only webcotel Support\nrun-name: webcotel Support Windows Build\non:\n  workflow_dispatch:\n\n', desc='workflow header')
    t = t.replace('VERSION: "${{ inputs.version }}"', 'VERSION: "1.5.0"')
    t = t.replace('STATUS_URL: "${{ secrets.GENURL }}/updategh"', 'STATUS_URL: ""')
    t = replace_once(t, r'^  setup:\s*\n.*?(?=^  generate-bridge:)', '', desc='RDGen ZIP setup job')
    t = t.replace('version: ${{ inputs.version }}', 'version: "1.5.0"')
    t = t.replace('rustdesk-version: ${{ inputs.version }}', 'rustdesk-version: "1.5.0"')
    t = t.replace('    needs: setup\n', '')
    t = t.replace('needs: [build-RustDeskTempTopMostWindow, generate-bridge, setup]', 'needs: [build-RustDeskTempTopMostWindow, generate-bridge]')

    cache = '''      - name: Export GitHub Actions cache environment variables
        uses: actions/github-script@v6
        with:
          script: |
            core.exportVariable('ACTIONS_CACHE_URL', process.env.ACTIONS_CACHE_URL || '');
            core.exportVariable('ACTIONS_RUNTIME_TOKEN', process.env.ACTIONS_RUNTIME_TOKEN || '');

'''
    t = replace_once(t, r'^      - name: Checkout Repository\s*\n.*?(?=^      - name: Checkout source code\s*$)',
                     cache, desc='encrypted ZIP and callback setup')
    own_config = '''      - name: Checkout webcotel configuration from this fork
        uses: actions/checkout@v4
        with:
          repository: ${{ github.repository }}
          ref: ${{ github.sha }}
          path: rdgen-config
          persist-credentials: false

      - name: Load webcotel configuration and validate branding
        shell: pwsh
        run: |
          python rdgen-config/scripts/load_webcotel_config.py --config rdgen-config/config/webcotel-support.json --assets rdgen-config/config/assets

'''
    t = replace_once(t, r'(?=^      - name: Restore bridge files\s*$)', own_config, desc='bridge insertion point')

    convert_icon = '''      - name: Prepare webcotel icons locally
        shell: pwsh
        timeout-minutes: 4
        run: |
          $ErrorActionPreference = "Stop"
          Copy-Item "res/icon.ico" "res/icon.ico.bak"
          Copy-Item "res/icon.png" "res/icon.png.bak"
          Copy-Item "res/tray-icon.ico" "res/tray-icon.ico.bak"
          Copy-Item "rdgen-config/config/assets/icon.png" "res/icon.png" -Force
          magick "res/icon.png" -define icon:auto-resize=256,128,96,64,48,40,32,24,20,16 "res/icon.ico"
          magick "res/icon.png" -resize 32x32 "res/tray-icon.ico"
          magick "res/icon.png" -resize 32x32 "res/32x32.png"
          magick "res/icon.png" -resize 64x64 "res/64x64.png"
          magick "res/icon.png" -resize 128x128 "res/128x128.png"
          magick "res/icon.png" -resize 256x256 "res/128x128@2x.png"
          Write-Host "webcotel icons prepared"

'''
    t = replace_once(t, r'^      - name: magick stuff\s*\n.*?(?=^      - name: ui\.rs icon\s*$)',
                     convert_icon, desc='icon download/conversion step')

    own_logo = '''      - name: Apply webcotel logo locally
        shell: pwsh
        run: |
          $ErrorActionPreference = "Stop"
          $out = "rustdesk/data/flutter_assets/assets"
          if (!(Test-Path $out)) { throw "Flutter assets missing" }
          Copy-Item "rdgen-config/config/assets/logo.png" "$out/logo.png" -Force
          # The PNG is preserved for later use. RDGen's Windows workflow does not
          # itself contain a privacy-screen wiring step, so do not claim it is active.
          Copy-Item "rdgen-config/config/assets/privacy.png" "$out/webcotel-privacy.png" -Force

'''
    t = replace_once(t, r'^      - name: logo stuff\s*\n.*?(?=^      - name: find Runner\.res\s*$)',
                     own_logo, desc='remote logo download step')

    artifact = '''      - name: Check generated support EXE
        shell: pwsh
        run: |
          $ErrorActionPreference = "Stop"
          $file = "SignOutput/${{ env.filename }}.exe"
          if (!(Test-Path $file)) { throw "Build failed: support EXE not found: $file" }
          $hash = Get-FileHash $file -Algorithm SHA256
          Write-Host "EXE: $file"
          Write-Host "SHA256: $($hash.Hash)"

      - name: Upload support EXE to GitHub Actions artifacts
        uses: actions/upload-artifact@v4
        with:
          name: webcotel-support-windows-${{ github.run_number }}
          path: SignOutput/${{ env.filename }}.exe
          if-no-files-found: error
          retention-days: 30
          compression-level: 0
'''
    t = replace_once(t, r'^      - name: send file to rdgen server\s*\n.*\Z', artifact,
                     desc='external callbacks/upload jobs')

    # Safety: refuse to leave any remote RDGen dependencies in the active Windows workflow.
    for forbidden in ('inputs.zip_url', 'secrets.GENURL', 'secrets.ZIP_PASSWORD', 'encrypted-secrets-zip',
                      '/save_custom_client', '/get_png?', '/cleanzip', 'needs: setup'):
        if forbidden in t:
            raise RuntimeError('Patch incomplete, found: ' + forbidden)
    if t.count('      - name: Load webcotel configuration') != 1:
        raise RuntimeError('Load-config step not uniquely inserted')
    backup = TARGET.with_suffix('.yml.before-webcotel.bak')
    if not backup.exists():
        shutil.copy2(TARGET, backup)
    TARGET.write_text(t, encoding='utf-8')
    print('PATCHED:', TARGET)
    print('Backup:', backup)
    print('Remaining workflow uses GitHub Actions only, with local branding and JSON settings.')


if __name__ == '__main__':
    main()
