"""Validate that error outputs do not contain stack traces or class names."""

from pathlib import Path

_PROJECT = Path(__file__).parent.parent.parent

_SERVICE_DIRS = [
    _PROJECT / "domain/pims/services",
    _PROJECT / "domain/analytics/services",
    _PROJECT / "domain/pims_ops/services",
    _PROJECT / "mcp_server/services",
]

_FORBIDDEN_IN_OUTPUT = [
    "Traceback",
    "HTTPStatusError",
    "httpx.HTTPStatusError",
]


def test_no_forbidden_in_output_assignments():
    """Check that 'output' or 'error' assignments don't contain forbidden patterns."""
    for svc_dir in _SERVICE_DIRS:
        if not svc_dir.exists():
            continue
        for pyfile in sorted(svc_dir.glob("*.py")):
            content = pyfile.read_text(encoding="utf-8")
            for forbidden in _FORBIDDEN_IN_OUTPUT:
                if forbidden not in content:
                    continue
                # Found a forbidden pattern — check if it's in output context
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if forbidden in line:
                        # Check if previous/next lines mention "output"
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        context = "\n".join(lines[start:end])
                        # Only flag if truly in output (not in try/except clause)
                        if (
                            '"output"' in context
                            or "'output'" in context
                        ):
                            if "output" not in line:
                                continue  # forbidden is in except clause, not output
                            raise AssertionError(
                                f"Forbidden pattern '{forbidden}' in output "
                                f"context in {pyfile} line {i+1}:\n{context}"
                            )
