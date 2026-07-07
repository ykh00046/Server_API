# tests/test_misc_coverage.py
"""Focused unit tests for small utility modules.

shared/path_setup.py, shared/metrics.py, shared/config.py helpers,
api/_gemini_client.py.
"""

import sys
from pathlib import Path

import pytest

from api import _gemini_client as gc
from shared import metrics as metrics_mod
from shared.config import _env_bool
from shared.metrics import PerformanceMonitor, TimedQuery
from shared.path_setup import (
    ensure_import_path,
    get_project_root,
    setup_path_for_file,
)


# ==========================================================
# path_setup
# ==========================================================
class TestPathSetup:
    def test_get_project_root(self):
        root = get_project_root()
        assert (root / "shared").is_dir()

    def test_ensure_import_path_idempotent(self):
        root = str(get_project_root())
        ensure_import_path(__file__)
        assert root in sys.path
        before = list(sys.path)
        # Second call must not duplicate the entry.
        ensure_import_path(__file__)
        assert sys.path.count(root) == before.count(root)

    def test_setup_path_for_subdir_file(self):
        # parent.name == 'api' is a recognized subdir, so project_root resolves
        # to the file's parent directory (the api/ dir itself).
        fake = get_project_root() / "api" / "main.py"
        root = setup_path_for_file(fake)
        assert root == fake.parent

    def test_setup_path_for_root_file(self, tmp_path):
        # A file with no 'shared' sibling and not in a known subdir name ->
        # project_root = parent.parent.
        nested = tmp_path / "pkg" / "mod.py"
        nested.parent.mkdir(parents=True)
        nested.write_text("x")
        root = setup_path_for_file(nested)
        assert root == tmp_path
        assert str(tmp_path) in sys.path


# ==========================================================
# config._env_bool (full-review-202607: case-insensitive opt-in parse)
# ==========================================================
class TestEnvBool:
    @pytest.mark.parametrize("raw", ["1", "true", "TRUE", "True", "yes", "ON"])
    def test_truthy_variants(self, monkeypatch, raw):
        monkeypatch.setenv("X_BOOL", raw)
        assert _env_bool("X_BOOL", default=False) is True

    @pytest.mark.parametrize("raw", ["0", "false", "FALSE", "Off", "No", " off "])
    def test_falsy_variants(self, monkeypatch, raw):
        # The old blocklist parse treated "FALSE"/"Off"/"No" as *enabled*.
        monkeypatch.setenv("X_BOOL", raw)
        assert _env_bool("X_BOOL", default=True) is False

    def test_unset_and_empty_use_default(self, monkeypatch):
        monkeypatch.delenv("X_BOOL", raising=False)
        assert _env_bool("X_BOOL", default=True) is True
        assert _env_bool("X_BOOL", default=False) is False
        monkeypatch.setenv("X_BOOL", "   ")
        assert _env_bool("X_BOOL", default=True) is True

    def test_unrecognized_falls_back_to_default(self, monkeypatch, caplog):
        monkeypatch.setenv("X_BOOL", "banana")
        with caplog.at_level("WARNING", logger="shared.config"):
            assert _env_bool("X_BOOL", default=False) is False
            assert _env_bool("X_BOOL", default=True) is True
        assert "not a recognized boolean" in caplog.text


# ==========================================================
# metrics
# ==========================================================
class TestMetrics:
    def test_empty_stats(self):
        pm = PerformanceMonitor()
        assert pm.get_stats("missing") == {}
        assert pm.get_all_stats() == {}

    def test_record_and_stats(self):
        pm = PerformanceMonitor()
        for d in (10.0, 20.0, 30.0):
            pm.record("q", duration_ms=d, row_count=5, cache_hit=False)
        pm.record("q", duration_ms=40.0, row_count=5, cache_hit=True)
        s = pm.get_stats("q")
        assert s["count"] == 4
        assert s["max_ms"] == 40.0
        assert s["cache_hit_rate"] == 25.0
        assert s["avg_rows"] == 5.0

    def test_single_sample_percentiles(self):
        pm = PerformanceMonitor()
        pm.record("solo", duration_ms=12.5)
        s = pm.get_stats("solo")
        assert s["p50_ms"] == 12.5
        assert s["p99_ms"] == 12.5

    def test_all_stats_multiple_groups(self):
        pm = PerformanceMonitor()
        pm.record("a", 1.0)
        pm.record("b", 2.0)
        all_stats = pm.get_all_stats()
        assert set(all_stats) == {"a", "b"}

    def test_reset(self):
        pm = PerformanceMonitor()
        pm.record("a", 1.0)
        pm.reset()
        assert pm.get_all_stats() == {}

    def test_timed_query_records(self):
        pm = metrics_mod.performance_monitor
        pm.reset()
        with TimedQuery("timed") as t:
            t.row_count = 3
            t.cache_hit = True
        s = pm.get_stats("timed")
        assert s["count"] == 1
        assert s["avg_rows"] == 3.0
        assert s["cache_hit_rate"] == 100.0
        pm.reset()


# ==========================================================
# _gemini_client
# ==========================================================
class TestGeminiClient:
    def test_get_client_no_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        gc.reset_for_tests()
        assert gc.get_client() is None
        # Cached path: second call returns the cached None without re-checking.
        assert gc.get_client() is None
        gc.reset_for_tests()

    def test_get_client_success(self, monkeypatch):
        sentinel = object()
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(gc.genai, "Client", lambda api_key: sentinel)
        gc.reset_for_tests()
        assert gc.get_client() is sentinel
        gc.reset_for_tests()

    def test_get_client_init_failure(self, monkeypatch):
        def _boom(api_key):
            raise ValueError("bad key")

        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(gc.genai, "Client", _boom)
        gc.reset_for_tests()
        assert gc.get_client() is None
        gc.reset_for_tests()

    def test_is_fallbackable_non_genai_error(self):
        assert gc.is_fallbackable(ValueError("nope")) is False

    def test_is_fallbackable_status_429(self):
        e = gc.ClientError.__new__(gc.ClientError)
        e.status = 429
        assert gc.is_fallbackable(e) is True

    def test_is_fallbackable_status_zero_message_match(self):
        e = gc.ServerError.__new__(gc.ServerError)
        e.status = 0
        e.args = ("503 Service Unavailable",)
        assert gc.is_fallbackable(e) is True

    def test_is_fallbackable_non_fallback_status(self):
        e = gc.ClientError.__new__(gc.ClientError)
        e.status = 400
        assert gc.is_fallbackable(e) is False


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
