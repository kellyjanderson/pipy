from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def install_systemd_service(*, start: bool = False) -> Path:
    if os.geteuid() != 0:
        raise PermissionError("service installation requires sudo/root")
    user = os.environ.get("SUDO_USER") or "root"
    pipy = shutil.which("pipy") or "/usr/local/bin/pipy"
    unit = Path("/etc/systemd/system/pipy.service")
    unit.write_text(
        f"""[Unit]\nDescription=PiPy distributed compute node\nAfter=network-online.target bluetooth.target\nWants=network-online.target bluetooth.target\n\n[Service]\nType=simple\nUser={user}\nExecStart={pipy} begin\nRestart=on-failure\nRestartSec=2\n\n[Install]\nWantedBy=multi-user.target\n""",
        encoding="utf-8",
    )
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "pipy.service"], check=True)
    if start:
        subprocess.run(["systemctl", "restart", "pipy.service"], check=True)
    return unit
