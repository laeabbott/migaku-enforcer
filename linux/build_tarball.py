#!/usr/bin/env python3
"""
Build the Linux installer tarball.

    python linux/build_tarball.py   ->  Output/migaku-enforcer-linux-<version>.tar.gz

Runs on Windows or Linux. The version comes from installer.iss (MyAppVersion), so
both platforms' release files always carry the same number. Text files get LF
line endings and executables get mode 755 whatever the checkout looks like, which
matters when building on Windows with core.autocrlf.
"""

import io
import re
import sys
import tarfile
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

APP_FILES = [
    "migaku_enforcer.py",
    "config_forms.py",
    "gui_theme.py",
    "onboarding_wizard.py",
    "settings_dialog.py",
    "install_startup.py",
    "uninstall_startup.py",
    "setup_credentials.py",
    "LICENSE",
]
APP_EXECUTABLES = [
    "linux/install.sh",
    "linux/uninstall.sh",
    "linux/migaku-hosts-helper",
]
TOP_LEVEL = {  # archive name -> (source, executable)
    "install.sh": ("linux/installer/install.sh", True),
    "uninstall.sh": ("linux/installer/uninstall.sh", True),
    "README.txt": ("linux/installer/README.txt", False),
    "LICENSE": ("LICENSE", False),
}


def read_version() -> str:
    text = (ROOT / "installer.iss").read_text(encoding="utf-8")
    m = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', text)
    if not m:
        sys.exit("Could not find MyAppVersion in installer.iss")
    return m.group(1)


def text_bytes(rel: str) -> bytes:
    data = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
    if rel.endswith((".sh", "migaku-hosts-helper")) and not data.startswith(b"#!"):
        sys.exit(f"{rel}: missing shebang")
    return data


def icon_png() -> bytes:
    with Image.open(ROOT / "assets" / "migaku_enforcer.ico") as ico:
        sizes = ico.info.get("sizes") or {ico.size}
        ico.size = max(sizes)
        img = ico.convert("RGBA")
    if img.size != (256, 256):
        img = img.resize((256, 256), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def add(tar: tarfile.TarFile, name: str, data: bytes, executable: bool, mtime: float) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o755 if executable else 0o644
    info.mtime = mtime
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    tar.addfile(info, io.BytesIO(data))


def add_dir(tar: tarfile.TarFile, name: str, mtime: float) -> None:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    info.mtime = mtime
    tar.addfile(info)


def main() -> None:
    version = read_version()
    top = f"migaku-enforcer-linux-{version}"
    out_dir = ROOT / "Output"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{top}.tar.gz"
    mtime = time.time()

    with tarfile.open(out, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        for d in ("", "/app", "/app/assets", "/app/linux"):
            add_dir(tar, top + d, mtime)
        for name, (src, exe) in TOP_LEVEL.items():
            data = text_bytes(src)
            if name == "install.sh":
                if b"@VERSION@" not in data:
                    sys.exit("install.sh: @VERSION@ placeholder missing")
                data = data.replace(b"@VERSION@", version.encode())
            add(tar, f"{top}/{name}", data, exe, mtime)
        for rel in APP_FILES:
            add(tar, f"{top}/app/{rel}", text_bytes(rel), False, mtime)
        for rel in APP_EXECUTABLES:
            add(tar, f"{top}/app/{rel}", text_bytes(rel), True, mtime)
        add(tar, f"{top}/app/assets/migaku-enforcer.png", icon_png(), False, mtime)

    print(out)


if __name__ == "__main__":
    main()
