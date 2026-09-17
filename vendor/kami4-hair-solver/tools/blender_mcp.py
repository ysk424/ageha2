"""Local Blender MCP bridge; null-delimited JSON, Blender main-thread execution."""

import argparse
import json
import socket
from pathlib import Path


def execute(code, port=9876, timeout=60):
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.settimeout(timeout)
        sock.sendall(
            json.dumps({"type": "execute", "strict_json": True, "code": code}).encode() + b"\0"
        )
        data = bytearray()
        while b"\0" not in data:
            chunk = sock.recv(1048576)
            if not chunk:
                raise ConnectionError("Blender closed the connection before its reply")
            data.extend(chunk)
    result = json.loads(data.split(b"\0", 1)[0])
    if result.get("status") != "ok":
        raise RuntimeError(result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("file", type=Path)
    p.add_argument("--port", type=int, default=9876)
    p.add_argument("--timeout", type=float, default=60)
    a = p.parse_args()
    print(
        json.dumps(
            execute(a.file.read_text(encoding="utf-8"), a.port, a.timeout),
            ensure_ascii=False,
            indent=2,
        )
    )
