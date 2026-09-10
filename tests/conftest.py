"""Pytest configuration and shared fixtures."""
from __future__ import annotations

# Use function-scope asyncio by default — avoids deprecation warnings
# and works with the STRICT mode installed by pytest-asyncio.
def pytest_configure(config):
    config.option.asyncio_mode = "auto"
