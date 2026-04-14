from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / 'version_info.txt'


def read_version() -> tuple[str, tuple[int, int, int, int]]:
    text = VERSION_FILE.read_text(encoding='utf-8')
    match = re.search(r"StringStruct\('FileVersion', '([0-9]+(?:\.[0-9]+){1,3})'\)", text)
    if not match:
        match = re.search(r"StringStruct\('ProductVersion', '([0-9]+(?:\.[0-9]+){1,3})'\)", text)
    if not match:
        raise RuntimeError('Cannot find version string in version_info.txt')
    version = match.group(1)
    parts = [int(p) for p in version.split('.')]
    while len(parts) < 4:
        parts.append(0)
    version_tuple = tuple(parts[:4])
    return version, version_tuple


def update_file(path: Path, pattern: str, repl: str) -> bool:
    text = path.read_text(encoding='utf-8')
    new_text, count = re.subn(pattern, repl, text, count=1, flags=re.M)
    if count:
        path.write_text(new_text, encoding='utf-8')
        return True
    return False


def main() -> int:
    version, version_tuple = read_version()
    changed = []

    if update_file(ROOT / 'ui_main.py', r'^APP_VERSION\s*=\s*"[^"]+"', f'APP_VERSION = "{version}"'):
        changed.append('ui_main.py')

    vi = VERSION_FILE.read_text(encoding='utf-8')
    tuple_repr = f'({version_tuple[0]}, {version_tuple[1]}, {version_tuple[2]}, {version_tuple[3]})'
    vi = re.sub(r'filevers=\([^)]*\)', f'filevers={tuple_repr}', vi, count=1)
    vi = re.sub(r'prodvers=\([^)]*\)', f'prodvers={tuple_repr}', vi, count=1)
    vi = re.sub(r"StringStruct\('FileVersion', '[^']+'\)", f"StringStruct('FileVersion', '{version}')", vi, count=1)
    vi = re.sub(r"StringStruct\('ProductVersion', '[^']+'\)", f"StringStruct('ProductVersion', '{version}')", vi, count=1)
    VERSION_FILE.write_text(vi, encoding='utf-8')
    changed.append('version_info.txt')

    update_file(ROOT / 'README.md', r'当前版本：\*\*[^*]+\*\*', f'当前版本：**{version}**') and changed.append('README.md')

    build_bat = ROOT / 'build_free_rename_exe.bat'
    text = build_bat.read_text(encoding='utf-8')
    text = re.sub(r'free_rename v[^\r\n]+ build', f'free_rename v{version} onedir build', text)
    build_bat.write_text(text, encoding='utf-8')
    changed.append('build_free_rename_exe.bat')

    print(f'[OK] Synced version to {version}')
    for item in changed:
        print(' -', item)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
