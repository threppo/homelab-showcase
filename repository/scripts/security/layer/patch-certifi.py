"""Patch trust data and verified offline wheels; invoke with python -I -S, never import packages."""
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

SOURCE = "/opt/homelab-ca/certifi-cacert.pem"
ROOTS = ("/usr/local/lib", "/usr/lib", "/opt", "/app", "/venv", "/venvs", "/home", "/root/.local")


def patch(roots, source):
    patched = 0
    sites = set()
    ensurepip_dirs = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [name for name in dirs if name not in {".git", "node_modules", ".cache"}]
            if os.path.basename(directory) in {"site-packages", "dist-packages"}:
                sites.add(Path(directory))
            if os.path.basename(directory) == "ensurepip" and "__init__.py" in files:
                ensurepip_dirs.add(Path(directory))
            if os.path.basename(directory) != "certifi" or "cacert.pem" not in files:
                continue
            target = os.path.join(directory, "cacert.pem")
            # Includes pip/_vendor/certifi and requests' vendored certifi.
            if os.path.realpath(target) == os.path.realpath(source):
                continue
            shutil.copyfile(source, target)
            print("trust-data-replaced\t" + target)
            patched += 1
    print("trust-data-replacements\t" + str(patched))
    # Wheels are downloaded and SHA-256 checked against PyPI metadata by the
    # maintenance preparer. Extract only these dependency-free public packages;
    # never execute a pre-existing pip or site startup hook.
    def install_wheel(wheel, target, package):
        with zipfile.ZipFile(wheel) as archive:
            members = archive.namelist()
            if any(Path(name).is_absolute() or ".." in Path(name).parts for name in members):
                raise RuntimeError("Unsafe wheel path")
            for old in list(target.glob(package + "-*.dist-info")) + list(target.glob(package + "-*.egg-info")):
                if old.is_dir():
                    shutil.rmtree(old)
                else:
                    old.unlink()
            archive.extractall(target)
        print("package-upgraded\t" + package + "\t" + str(target))

    certifi_wheel = Path("/opt/homelab-ca/certifi-2026.10.19-py3-none-any.whl")
    pip_wheel = Path("/opt/homelab-ca/pip-26.2.2-py3-none-any.whl")
    for site in sorted(sites):
        if certifi_wheel.exists() and (site / "certifi").is_dir():
            install_wheel(certifi_wheel, site, "certifi")
        if pip_wheel.exists() and sys.version_info >= (3, 9) and (site / "pip").is_dir():
            install_wheel(pip_wheel, site, "pip")
    if pip_wheel.exists() and sys.version_info >= (3, 9):
        for directory in ensurepip_dirs:
            bundled = directory / "_bundled"
            if not bundled.is_dir():
                continue
            init = directory / "__init__.py"
            text = init.read_text()
            revised, count = re.subn(r'''(_PIP_VERSION\s*=\s*)["'][^"']+["']''', r'\1"26.2.2"', text)
            if count != 1:
                raise RuntimeError("Unexpected ensurepip version declaration")
            shutil.copyfile(pip_wheel, bundled / pip_wheel.name)
            for old in bundled.glob("pip-*.whl"):
                if old.name != pip_wheel.name:
                    old.unlink()
            init.write_text(revised)
            print("ensurepip-upgraded\t" + str(directory))


if __name__ == "__main__":
    if not sys.flags.isolated or not sys.flags.no_site:
        raise SystemExit("Invoke with -I -S to disable startup hooks")
    if not os.path.isfile(SOURCE) or os.path.getsize(SOURCE) == 0:
        raise SystemExit("Verified certifi CA bundle missing or empty")
    patch(ROOTS, SOURCE)
