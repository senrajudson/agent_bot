"""Valida entrypoint canônico e fail-fast para comando legado."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_MINIMAL_ENV = {
    **os.environ,
    "MCP_PORT": "0",
    "ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY": "false",
    "ENABLE_DRIVE_CSV_EXPORT_TOOL": "false",
    "ENABLE_TEST_ARTIFACT_TOOL": "false",
    "ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV": "false",
    "ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND": "false",
    "PI_WEB_API_BASE_URL": "http://localhost:1",
    "MATH_TOOL_BASE_URL": "http://localhost:1",
}


def test_canonical_entrypoint_starts():
    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_server.server"],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_MINIMAL_ENV,
    )
    try:
        # Wait a few seconds for the server to start or crash
        try:
            proc.wait(timeout=6)
            # Process exited — check if it was an error
            stderr_text = proc.stderr.read().decode(errors="replace")
            assert "ModuleNotFoundError" not in stderr_text, (
                f"ModuleNotFoundError during startup:\n{stderr_text}"
            )
        except subprocess.TimeoutExpired:
            # Process is still running — that means startup succeeded
            stderr_text = b""
            pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)


def test_legacy_script_fails_with_message():
    result = subprocess.run(
        [sys.executable, "mcp_server/server.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=10,
        env=_MINIMAL_ENV,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"Legacy script should fail, got exit code 0"
    )
    assert "poetry run python -m mcp_server.server" in output, (
        f"Missing orientative message in output:\n{output}"
    )
    assert "ModuleNotFoundError" not in output, (
        f"ModuleNotFoundError should not appear:\n{output}"
    )
