"""Fixtures for tests that run a real bridge inside a test Home Assistant."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def bridge_env(mock_async_zeroconf: MagicMock, socket_enabled: None) -> Generator[None]:
    """Let the HAP server bind to localhost only."""
    with (
        patch(
            "custom_components.homekit_alchemy.manager.network.async_get_announce_addresses",
            return_value=["127.0.0.1"],
        ),
        patch("custom_components.homekit_alchemy.manager.BIND_ADDRESS", ["127.0.0.1"]),
    ):
        yield
