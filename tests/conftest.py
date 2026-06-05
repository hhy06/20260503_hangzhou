"""Shared fixtures and invariant helpers for warehouse simulation tests."""

from collections.abc import Generator

import pytest
import salabim as sim


# ---------------------------------------------------------------------------
# salabim environment for unit tests (function-scoped)
# ---------------------------------------------------------------------------

@pytest.fixture
def env() -> Generator[sim.Environment, None, None]:
    _env = sim.Environment(trace=False)
    yield _env
