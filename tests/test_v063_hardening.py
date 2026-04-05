"""
Regression tests for v0.6.3 — Test Suite Hardening.

Verifies fixes for GitHub Issue #2 (SoliareofAstora):
  1. Degenerate assertions replaced with meaningful checks
  2. Silent-pass guards replaced with explicit preconditions
  3. Import failure logging added
  4. Z3 timeouts consolidated into configurable constants
"""

import logging
import re
from unittest.mock import patch

import pytest

from axiomguard.tournament import (
    Tournament,
    Z3_CONFLICT_TIMEOUT_MS,
    Z3_REDUNDANCY_TIMEOUT_MS,
)
from axiomguard.z3_engine import Z3_DEFAULT_TIMEOUT_MS


# =====================================================================
# Fixtures
# =====================================================================

def _mock_llm(prompt: str) -> str:
    """Minimal mock for tournament generation."""
    if "Hard Constraints" in prompt:
        return """
axiomguard: "0.3"
domain: test
rules:
  - name: c_min_age
    type: range
    entity: person
    relation: age
    value_type: int
    min: 18
    severity: error
    message: "Must be 18+."
"""
    if "Exceptions" in prompt:
        return """
axiomguard: "0.3"
domain: test
rules:
  - name: x_minor_override
    type: range
    entity: person
    relation: age
    value_type: int
    min: 16
    severity: error
    message: "With parental consent, 16+."
"""
    return """
axiomguard: "0.3"
domain: test
rules:
  - name: fallback_rule
    type: unique
    entity: person
    relation: name
    severity: error
    message: "One name only."
"""


# =====================================================================
# 1. Degenerate Assertion Regression
# =====================================================================

class TestDegenerateAssertionFix:
    """Verify old tautology assertions (>= 0) are replaced."""

    def test_old_assertion_is_tautology(self):
        """Prove that the old pattern can never fail."""
        assert len([]) >= 0        # always true
        assert len([1, 2]) >= 0    # always true
        assert 0 >= 0              # always true

    def test_new_assertion_catches_empty(self):
        """Prove that the new pattern fails on empty."""
        with pytest.raises(AssertionError):
            items = []
            assert len(items) > 0, "Expected non-empty"

    def test_tournament_conflicts_are_detected(self):
        """Tournament with competing strategies MUST produce conflicts."""
        t = Tournament(source="test", strategies=["constraints", "exceptions"])
        t.generate(llm_generate=_mock_llm)
        t.detect_conflicts()
        conflicts = t.conflicts()
        assert len(conflicts) > 0, "Competing strategies should produce conflicts"

    def test_tournament_standalone_exist(self):
        """Tournament with multiple strategies MUST have standalone candidates."""
        t = Tournament(
            source="test",
            strategies=["constraints", "exceptions", "adversarial"],
        )
        t.generate(llm_generate=_mock_llm)
        t.detect_conflicts()
        count = t.approve_all_standalone()
        assert count > 0, "Should have standalone candidates to approve"


# =====================================================================
# 2. Silent-Pass Guard Regression
# =====================================================================

class TestSilentPassGuardFix:
    """Verify test preconditions are enforced, not silently skipped."""

    def test_conflicts_precondition_enforced(self):
        """If conflicts were empty, old code silently passed. New code must fail."""
        t = Tournament(source="test", strategies=["constraints", "exceptions"])
        t.generate(llm_generate=_mock_llm)
        t.detect_conflicts()

        conflicts = t.conflicts()
        # This assertion is the fix — old code had `if conflicts:` instead
        assert len(conflicts) > 0, "Setup failed: no conflicts generated"

    def test_standalone_precondition_enforced(self):
        """If standalone was empty, old code silently passed."""
        t = Tournament(
            source="test",
            strategies=["constraints", "exceptions", "adversarial"],
        )
        t.generate(llm_generate=_mock_llm)
        t.detect_conflicts()

        standalone = t.standalone_candidates()
        assert len(standalone) > 0, "Setup failed: no standalone candidates"


# =====================================================================
# 3. Import Failure Logging Regression
# =====================================================================

class TestImportLogging:
    """Verify logging.debug() fires on ImportError."""

    def test_anthropic_import_failure_logs(self):
        """When anthropic import fails, should log debug message."""
        import os
        os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-test"

        with patch("builtins.__import__", side_effect=_selective_import_error("anthropic")):
            with patch("logging.Logger.debug") as mock_debug:
                try:
                    from axiomguard.rule_generator import _get_default_llm
                    _get_default_llm()
                except (RuntimeError, ImportError):
                    pass
                # Check that debug was called with anthropic message
                debug_calls = [str(c) for c in mock_debug.call_args_list]
                has_anthropic_log = any("anthropic" in c for c in debug_calls)
                assert has_anthropic_log, f"Expected anthropic debug log, got: {debug_calls}"

        os.environ.pop("ANTHROPIC_API_KEY", None)


def _selective_import_error(block_module: str):
    """Create an import function that blocks a specific module."""
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _fake_import(name, *args, **kwargs):
        if name == block_module:
            raise ImportError(f"Simulated: No module named {block_module}")
        return real_import(name, *args, **kwargs)

    return _fake_import


# =====================================================================
# 4. Z3 Timeout Constants Regression
# =====================================================================

class TestZ3TimeoutConstants:
    """Verify timeouts are configurable, not hardcoded."""

    def test_default_timeout_value(self):
        assert Z3_DEFAULT_TIMEOUT_MS == 2000

    def test_conflict_timeout_value(self):
        assert Z3_CONFLICT_TIMEOUT_MS == 500

    def test_redundancy_timeout_value(self):
        assert Z3_REDUNDANCY_TIMEOUT_MS == 200

    def test_constants_are_importable(self):
        """Users can import and override constants."""
        import axiomguard.z3_engine as z3e
        old = z3e.Z3_DEFAULT_TIMEOUT_MS
        z3e.Z3_DEFAULT_TIMEOUT_MS = 9999
        assert z3e.Z3_DEFAULT_TIMEOUT_MS == 9999
        z3e.Z3_DEFAULT_TIMEOUT_MS = old  # restore

    def test_no_hardcoded_timeouts_in_source(self):
        """Grep source files — no timeout_ms=NUMBER should remain."""
        import pathlib

        src_dir = pathlib.Path(__file__).parent.parent / "axiomguard"
        pattern = re.compile(r"timeout_ms\s*[:=]\s*\d+")

        violations = []
        for py_file in src_dir.glob("*.py"):
            for i, line in enumerate(py_file.read_text().splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("Z3_"):
                    continue
                if pattern.search(line):
                    violations.append(f"{py_file.name}:{i}: {stripped}")

        assert violations == [], f"Hardcoded timeouts found:\n" + "\n".join(violations)

    def test_knowledge_base_uses_constant(self):
        """KnowledgeBase.verify default timeout matches Z3_DEFAULT_TIMEOUT_MS."""
        import inspect
        from axiomguard.knowledge_base import KnowledgeBase

        sig = inspect.signature(KnowledgeBase.verify)
        default = sig.parameters["timeout_ms"].default
        assert default == Z3_DEFAULT_TIMEOUT_MS, (
            f"KB.verify default ({default}) != Z3_DEFAULT_TIMEOUT_MS ({Z3_DEFAULT_TIMEOUT_MS})"
        )
