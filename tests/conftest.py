"""Pytest configuration and common fixtures for pymotivaxmc2 tests."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock


# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
def mock_socket_manager():
    """Create a mock socket manager for testing."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def mock_protocol():
    """Create a mock protocol for testing."""
    mock = AsyncMock()
    mock.protocol_version = "3.1"
    return mock


@pytest.fixture
def mock_dispatcher():
    """Create a mock dispatcher for testing."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def sample_device_info():
    """Sample device discovery information."""
    return {
        "protocolVersion": "3.1",
        "controlPort": 7002,
        "notifyPort": 7003,
        "menuNotifyPort": 7003,
        "name": "XMC-2",
        "model": "XMC-2",
        "version": "2.0",
    } 