"""Check whether a TCP port is already bound on this host."""
from __future__ import annotations

import socket


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return False
        except OSError:
            return True


def find_listening_pid_windows(port: int) -> int | None:
    """Return PID listening on ``port`` (Windows netstat), or None."""
    import subprocess

    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    needle = f":{port}"
    for line in out.splitlines():
        if "LISTENING" not in line or needle not in line:
            continue
        parts = line.split()
        if parts:
            try:
                return int(parts[-1])
            except ValueError:
                continue
    return None
