import io
import json
from pathlib import Path
import shutil
import uuid
import zipfile

from fastapi.testclient import TestClient

import app as app_module
from app import app


client = TestClient(app)


def test_prepare_ligand_batch_endpoint_returns_zip_with_pdbqt_files_and_summary(monkeypatch):
    fixture_path = Path(__file__).parent / "fixtures" / "small_library.smi"
    temp_root = Path("tmp_test") / "prepare_ligand_batch_endpoint"
    temp_root.mkdir(parents=True, exist_ok=True)

    class WorkspaceTemporaryDirectory:
        def __init__(self):
            self.name = str(temp_root / f"tmp_{uuid.uuid4().hex}")

        def __enter__(self):
            Path(self.name).mkdir(parents=True, exist_ok=False)
            return self.name

        def __exit__(self, exc_type, exc, traceback):
            shutil.rmtree(self.name, ignore_errors=True)

    monkeypatch.setattr(app_module.tempfile, "TemporaryDirectory", WorkspaceTemporaryDirectory)

    with fixture_path.open("rb") as ligand_file:
        response = client.post(
            "/prepare_ligand_batch",
            data={
                "filename": "small_library",
                "charge_model": "zero",
            },
            files={
                "file": ("small_library.smi", ligand_file, "text/plain"),
            },
        )

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/zip"
    assert ".zip" in response.headers["Content-Disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        archive_names = zip_file.namelist()
        pdbqt_names = [name for name in archive_names if name.endswith(".pdbqt")]

        assert pdbqt_names
        assert "summary.json" in archive_names

        summary = json.loads(zip_file.read("summary.json").decode("utf-8"))

    assert summary["total"] == 2
    assert summary["successful"] == 2
    assert summary["failed"] == 0
