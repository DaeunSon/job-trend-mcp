import os
import subprocess
import sys


def test_import_without_pythonpath(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, "-c", "import src.mcp_server.run, src.normalization, evals"],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
