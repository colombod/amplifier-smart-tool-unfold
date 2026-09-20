"""Launch actual Node processes without shell wrappers or command interpolation."""

import json
import shutil

import pytest

from unfold.backend import Backend
from unfold.models import UnfoldError


@pytest.fixture
def backend(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Install Node to run backend portability checks")
    backend = Backend(tmp_path / "backend with spaces")
    backend.cli.parent.mkdir(parents=True)
    return backend


def test_launcher_preserves_arguments_and_scrubs_environment(backend, monkeypatch):
    backend.cli.write_text("""
console.log(JSON.stringify({
  args: process.argv.slice(2),
  secret: process.env.OPENAI_API_KEY ?? null,
  options: process.env.NODE_OPTIONS ?? null,
  temp: process.env.TEMP,
  telemetry: process.env.HYPERFRAMES_NO_TELEMETRY
}));
""")
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv("NODE_OPTIONS", "--invalid-option-must-not-be-inherited")
    monkeypatch.setenv("TEMP", str(backend.root.parent))
    arguments = ["render", "directory with spaces", "--output", "clip & (final).mp4", "$HOME"]
    result = json.loads(backend._run_cli(arguments))
    assert result["args"] == arguments
    assert result["secret"] is None
    assert result["options"] is None
    assert result["temp"] == str(backend.root.parent)
    assert result["telemetry"] == "1"


def test_launcher_reports_process_failure(backend):
    backend.cli.write_text('console.error("render failure"); process.exitCode = 7;')
    with pytest.raises(UnfoldError, match="render failure"):
        backend._run_cli(["render"])
