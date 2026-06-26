import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_password")
os.environ.setdefault("POSTGRES_DB", "test_db")
os.environ.setdefault("SECRET_KEY", "super-secret-test-key-for-testing-only-12345")
os.environ.setdefault("SMTP_USER", "test_smtp")
os.environ.setdefault("SMTP_PASSWORD", "test_smtp_pass")
os.environ.setdefault("SMTP_FROM_EMAIL", "test@example.com")
os.environ.setdefault("VECTOR_DB_CONNECTION_STRING", "postgresql://localhost:5432/test")
os.environ.setdefault("SHOPEASY_API_KEY", "test-key")
os.environ.setdefault("DB_USER", "testuser")
os.environ.setdefault("DB_PASS", "testpass")
os.environ.setdefault("ADMIN_RPC_KEY", "test-admin-key")
os.environ.setdefault("OLLAMA_API_KEY", "test-ollama-key")


PROJECT_ROOT = Path(__file__).resolve().parent.parent


if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def project_root():
    """Returns the absolute path to the Backend/ directory."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def tests_dir(project_root):
    """Returns the absolute path to the Backend/tests/ directory."""
    return project_root / "tests"


@pytest.fixture(scope="session")
def data_dir(project_root):
    """
    Returns the absolute path to the Backend/data/ directory.
    (Fixed: Your project tree shows 'data' at the root, not inside 'tests')
    """
    return project_root / "tests/data"


@pytest.fixture
def load_json(data_dir):
    """Helper fixture to load JSON files from the data directory."""
    def _load(rel_path):
        with open(data_dir / rel_path, "r") as f:
            return json.load(f)
    return _load


@pytest.fixture
def write_temp_json(tmp_path):
    """Helper fixture to write temporary JSON files during tests."""
    def _write(data, filename="config.json"):
        path = tmp_path / filename
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return str(path)
    return _write


# --- Mocking Fixtures ---

@pytest.fixture
def mock_requests():
    with patch("ai_engine.action_engine.requests.request") as m:
        yield m


@pytest.fixture
def mock_generate_embedding():
    with patch("ai_engine.action_engine.generate_embedding") as m:
        m.return_value = [0.1, 0.2, 0.3]
        yield m


@pytest.fixture
def mock_get_vector_driver():
    with patch("ai_engine.action_engine.get_vector_driver") as m:
        driver = MagicMock()
        driver.search.return_value = [{"id": 1, "name": "Product"}]
        m.return_value = driver
        yield m


@pytest.fixture
def mock_grpc_insecure_channel():
    with patch("ai_engine.action_engine.grpc.insecure_channel") as m:
        yield m