import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.request import urlopen

import pytest


@pytest.fixture
def backend(tmp_path):
    shutil.copy(Path(__file__).parents[1] / "voice_game.sh", tmp_path)
    (tmp_path / "config").mkdir()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    (tmp_path / "config/backend.conf").write_text(f"PORT={port}\n")
    (tmp_path / "requirements.txt").write_text("uvicorn>=0.27.0\n")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/main.py").write_text('''import asyncio
import json
import os

async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        await receive()
        await send({"type": "lifespan.startup.complete"})
        await receive()
        await asyncio.sleep(0.4)
        await send({"type": "lifespan.shutdown.complete"})
        return
    body = json.dumps({"enabled": os.getenv("JEV_DEBUG") == "true"}).encode()
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": body})
''')

    def command(action, debug="false"):
        return subprocess.run(
            ["bash", "voice_game.sh", action], cwd=tmp_path,
            env={**os.environ, "JEV_DEBUG": debug}, capture_output=True,
            text=True, timeout=30,
        )

    yield tmp_path, port, command
    command("stop")


def test_start_rejects_unmanaged_listener(backend):
    root, port, command = backend
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
        listener.listen()
        result = command("start", "true")
        assert result.returncode != 0, result.stdout
        assert "already in use" in result.stderr
        assert not (root / ".backend.pid").exists()
        assert listener.getsockname()[1] == port


def test_restart_waits_for_shutdown_and_new_environment(backend):
    root, port, command = backend
    started = command("start")
    assert started.returncode == 0, started.stderr
    with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
        assert json.load(response) == {"enabled": False}
    restarted = command("restart", "true")
    assert restarted.returncode == 0, restarted.stderr
    with urlopen(f"http://127.0.0.1:{port}/api/debug/jev", timeout=2) as response:
        assert json.load(response) == {"enabled": True}
    stopped = command("stop")
    assert stopped.returncode == 0, stopped.stderr
    assert not (root / ".backend.pid").exists()
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_start_reports_server_exit(backend):
    root, port, command = backend
    (root / "backend/main.py").write_text('raise RuntimeError("startup failed")\n')
    result = command("start")
    assert result.returncode != 0, result.stdout
    assert "failed to start" in result.stderr
    assert not (root / ".backend.pid").exists()
