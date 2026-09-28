#!/usr/bin/env python3
"""Read-only checks: do not install dependencies or start/build any container."""
import json
import platform
import shutil
import subprocess
from pathlib import Path

errors = []
def check(ok, message):
    print(('OK   ' if ok else 'FAIL ') + message)
    if not ok:
        errors.append(message)

check(platform.machine() == 'aarch64', 'Server must be native ARM64 (aarch64).')
mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
available = int(mem['MemAvailable'].split()[0]) // 1024
check(available >= 512, f'Available RAM {available} MiB; at least 512 MiB required before starting CMS.')
free = shutil.disk_usage(Path(__file__).resolve().parent.parent).free // (1024**3)
check(free >= 2, f'Free disk {free} GiB; at least 2 GiB required.')
for zone in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
    temp = int(zone.read_text()) / 1000
    check(temp < 75, f'Temperature {temp:.1f} C; must be below 75 C.')
image = subprocess.run(['docker', 'image', 'inspect', 'hydroflow-landing-cms-cms:latest'], capture_output=True, text=True)
check(image.returncode == 0, 'Prebuilt CMS image exists locally; deployment never builds or pulls.')
if image.returncode == 0:
    check(json.loads(image.stdout)[0]['Architecture'] == 'arm64', 'Image architecture is arm64.')
check(Path('.env').is_file(), '.env exists.')
if errors:
    raise SystemExit('Deployment checks failed. Resolve the reported conditions first.')
print('Preflight passed. These checks reduce risk; they cannot prove host stability.')
