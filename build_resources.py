from __future__ import annotations

import os
import shutil
import site
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QRC = ROOT / "resources.qrc"
OUT = ROOT / "resources_rc.py"


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _candidate_script_dirs() -> list[Path]:
    dirs: list[Path] = []

    # sysconfig may point to the system Scripts dir even when packages are installed with --user.
    try:
        scripts_dir = sysconfig.get_path("scripts")
        if scripts_dir:
            dirs.append(Path(scripts_dir))
    except Exception:
        pass

    try:
        user_base = site.getuserbase()
        if user_base:
            dirs.append(Path(user_base) / ("Scripts" if os.name == "nt" else "bin"))
    except Exception:
        pass

    try:
        user_site = site.getusersitepackages()
        if user_site:
            us = Path(user_site)
            # .../site-packages -> sibling Scripts/bin
            dirs.append(us.parent / ("Scripts" if os.name == "nt" else "bin"))
    except Exception:
        pass

    py = Path(sys.executable).resolve()
    dirs.extend([py.parent, py.parent / "Scripts"])

    if os.name == "nt":
        home = Path.home()
        ver = f"Python{sys.version_info.major}{sys.version_info.minor}"
        dirs.append(home / "AppData" / "Roaming" / "Python" / ver / "Scripts")

    return _dedupe(dirs)


def _candidate_package_dirs() -> list[Path]:
    dirs: list[Path] = []
    try:
        import PySide6  # type: ignore
        pkg = Path(PySide6.__file__).resolve().parent
        dirs.extend(
            [
                pkg,
                pkg / "scripts",
                pkg / "Qt",
                pkg / "Qt" / "bin",
                pkg / "Qt" / "libexec",
            ]
        )
    except Exception:
        pass
    return _dedupe(dirs)


def find_rcc() -> tuple[list[str] | None, list[str]]:
    searched: list[str] = []

    # 1) PATH
    for name in ("pyside6-rcc", "pyside6-rcc.exe"):
        path = shutil.which(name)
        if path:
            return [path], searched

    # 2) likely Scripts dirs
    for script_dir in _candidate_script_dirs():
        searched.append(str(script_dir))
        for name in ("pyside6-rcc.exe", "pyside6-rcc"):
            path = script_dir / name
            if path.exists():
                return [str(path)], searched

    # 3) bundled package locations
    # Prefer the wrapper, but fall back to rcc with Python generator.
    for pkg_dir in _candidate_package_dirs():
        searched.append(str(pkg_dir))
        for name in ("pyside6-rcc.exe", "pyside6-rcc"):
            path = pkg_dir / name
            if path.exists():
                return [str(path)], searched

    for pkg_dir in _candidate_package_dirs():
        for path in list(pkg_dir.glob("rcc.exe")) + list(pkg_dir.glob("rcc")):
            if path.exists():
                # rcc has Python support; use it directly if the wrapper script is missing.
                return [str(path), "-g", "python"], searched

    return None, searched


def main() -> int:
    if not QRC.exists():
        print(f"[ERROR] resource file not found: {QRC}")
        return 1

    cmd, searched = find_rcc()
    if not cmd:
        print("[ERROR] pyside6-rcc not found.")
        print("[INFO] Searched locations:")
        for p in searched:
            print(" -", p)
        print("[HINT] Run:")
        print("       py -3 -c \"import site,sysconfig; print('sysconfig=', sysconfig.get_path('scripts')); print('userbase=', site.getuserbase()); print('usersite=', site.getusersitepackages())\"")
        print("[HINT] Check whether pyside6-rcc.exe exists under the user's Scripts directory.")
        return 1

    full_cmd = cmd + ["-o", str(OUT), str(QRC)]
    print("[INFO] Compile Qt resources:", " ".join(full_cmd))
    result = subprocess.run(full_cmd, cwd=str(ROOT))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
