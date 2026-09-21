import subprocess
from pathlib import Path


def test_browser_controller_smoke():
    result = subprocess.run(
        ["node", str(Path(__file__).with_name("browser_controller_smoke.js"))],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "browser controller smoke: passed" in result.stdout
