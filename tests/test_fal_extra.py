"""``fal-client`` is the optional ``falaw[fal]`` extra, not a core dependency.

A caller that only builds, prices, hashes and caches plans (``nw``, and through
it the animation genre, which never makes a paid call) must be able to install
falaw with no fal.ai client. These tests run in a *subprocess* with
``fal_client`` (and ``httpx``, which rides in with it) blocked at the import
system, so a stray top-level import anywhere in falaw fails here and not on a
user's machine; the in-process suite cannot see that, because it has
``fal_client`` installed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

_BLOCK = textwrap.dedent(
    """
    import sys

    class _Block:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in ("fal_client", "httpx"):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    sys.meta_path.insert(0, _Block())
    """
)


def _run(body: str, tmp_path) -> subprocess.CompletedProcess:
    code = _BLOCK + textwrap.dedent(body)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        cwd=str(tmp_path),
        timeout=120,
    )


def test_planning_pricing_and_hashing_need_no_fal_client(tmp_path):
    proc = _run(
        """
        import falaw
        from falaw import Plan, plan_generate_image, plan_hash
        import falaw.testing  # noqa: F401

        call = plan_generate_image("a tiger eye, macro", quality="fast")
        plan = Plan(calls=(call,))
        assert plan.total_cost_usd >= 0
        assert len(plan_hash(plan)) > 8
        assert "fal_client" not in sys.modules
        assert "httpx" not in sys.modules
        print("ok")
        """,
        tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("ok")


def test_the_first_real_call_names_the_extra(tmp_path):
    proc = _run(
        """
        import falaw
        from falaw import FalClientNotInstalled, call_fal

        try:
            call_fal("fal-ai/flux/dev", {"prompt": "x"}, journal_errors=False)
        except FalClientNotInstalled as e:
            assert isinstance(e, ImportError)
            assert "pip install 'falaw[fal]'" in str(e), str(e)
            print("named")
        else:
            raise SystemExit("call_fal did not raise")
        """,
        tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("named")


def test_the_fetching_helpers_name_the_extra_too(tmp_path):
    proc = _run(
        """
        from falaw.errors import FalClientNotInstalled, import_httpx
        try:
            import_httpx("refreshing fal.ai prices")
        except FalClientNotInstalled as e:
            assert "falaw[fal]" in str(e)
            print("named")
        """,
        tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("named")


def test_the_extra_is_declared_in_the_metadata():
    """Core dependencies carry no fal-client; the ``fal`` extra does."""
    from pathlib import Path

    tomllib = pytest.importorskip("tomllib")  # stdlib from py3.11

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    meta = tomllib.loads(pyproject.read_text())["project"]
    assert not any(d.startswith("fal-client") for d in meta["dependencies"])
    assert any(d.startswith("fal-client") for d in meta["optional-dependencies"]["fal"])


def test_a_named_error_is_an_import_error():
    from falaw import FalClientNotInstalled, FalError

    assert issubclass(FalClientNotInstalled, (ImportError, FalError))
