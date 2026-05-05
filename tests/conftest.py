import sys
import shutil
import uuid
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def workspace_tempdir(monkeypatch):
    def apply(module, name: str):
        temp_root = PROJECT_ROOT / "tmp_test" / name
        temp_root.mkdir(parents=True, exist_ok=True)

        class WorkspaceTemporaryDirectory:
            def __init__(self):
                self.name = str(temp_root / f"tmp_{uuid.uuid4().hex}")

            def __enter__(self):
                Path(self.name).mkdir(parents=True, exist_ok=False)
                return self.name

            def __exit__(self, exc_type, exc, traceback):
                shutil.rmtree(self.name, ignore_errors=True)

        monkeypatch.setattr(module.tempfile, "TemporaryDirectory", WorkspaceTemporaryDirectory)
        return temp_root

    return apply
