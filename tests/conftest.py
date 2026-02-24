import pytest
from pathlib import Path


@pytest.fixture
def tmp_project(tmp_path):
    """A temporary project directory for testing."""
    return tmp_path


@pytest.fixture(autouse=True)
def chromadb_onnx_cache(monkeypatch):
    """Redirect ChromaDB ONNX model cache to a writable location.

    The default cache path (/Users/.../.cache/chroma/onnx_models) may be
    owned by root in some environments, causing PermissionError when ChromaDB
    tries to download the embedding model. This fixture redirects the download
    path to /tmp/chromadb_test_onnx where the model is pre-cached.

    This fixture runs automatically for all tests (autouse=True).
    """
    try:
        import chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 as ef_module
        monkeypatch.setattr(
            ef_module.ONNXMiniLM_L6_V2,
            "DOWNLOAD_PATH",
            "/tmp/chromadb_test_onnx",
        )
    except (ImportError, AttributeError):
        pass  # chromadb not installed or API changed — skip gracefully
