import pytest
from pathlib import Path


@pytest.fixture
def tmp_project(tmp_path):
    """A temporary project directory for testing."""
    return tmp_path
