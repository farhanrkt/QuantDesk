"""The runtime dependencies are audited, and stay on versions that were.

WHY A TEST FOR A WORKFLOW FILE. In November 2026 `pip-audit` found eighteen
known advisories in three runtime packages. CI had an audit job and it looked
only at npm, so the Python half — the half that computes every number — had
gone unexamined for as long as it had existed. The audit step is one line that
a later tidy-up could drop without anything turning red, and then the backlog
is invisible again. This is what turns red.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split(".")[:3] if part.isdigit())


def test_ci_audits_the_python_runtime_requirements():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "pip-audit -r requirements.txt" in workflow, (
        "CI must audit requirements.txt; npm audit alone leaves the API unexamined.")


def test_the_installed_starlette_has_the_host_header_fix():
    """The rate limiter reads the raw path because Starlette once rebuilt the
    URL from an unvalidated Host header. The library fixed it in 1.3.0, and
    FastAPI 0.115 could not install that. The pin must not slide back."""
    import starlette

    assert _version(starlette.__version__) >= (1, 3, 1)


def test_the_pins_are_the_versions_the_audit_cleared():
    pins = dict(line.split("==") for line in
                (ROOT / "requirements.txt").read_text().split() if "==" in line)
    assert _version(pins["fastapi"]) >= (0, 162, 7)
    assert _version(pins["lxml"]) >= (6, 1, 0)
    assert _version(pins["certifi"]) >= (2026, 10, 18)
