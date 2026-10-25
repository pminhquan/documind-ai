"""Shared pytest fixtures."""

import pytest
from PIL import Image


@pytest.fixture
def sample_png(tmp_path):
    """A tiny valid RGB PNG image."""
    path = tmp_path / "sample.png"
    Image.new("RGB", (32, 32), color="white").save(path, format="PNG")
    return path
