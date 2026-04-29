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


def use_workspace_temporary_directory(monkeypatch, name: str):
    temp_root = Path("tmp_test") / name
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


def test_prepare_ligand_rejects_empty_upload(monkeypatch):
    use_workspace_temporary_directory(monkeypatch, "prepare_ligand_empty_upload")

    response = client.post(
        "/prepare_ligand",
        data={
            "filename": "empty",
            "charge_model": "zero",
        },
        files={
            "file": ("empty.smi", io.BytesIO(b""), "text/plain"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty"


def test_prepare_ligand_batch_rejects_empty_upload(monkeypatch):
    use_workspace_temporary_directory(monkeypatch, "prepare_ligand_batch_empty_upload")

    response = client.post(
        "/prepare_ligand_batch",
        data={
            "filename": "empty_library",
            "charge_model": "zero",
        },
        files={
            "file": ("empty_library.smi", io.BytesIO(b""), "text/plain"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty"


def test_prepare_ligand_batch_reports_failed_count_for_invalid_smiles(monkeypatch):
    use_workspace_temporary_directory(monkeypatch, "prepare_ligand_batch_invalid_smiles")

    response = client.post(
        "/prepare_ligand_batch",
        data={
            "filename": "mixed_library",
            "charge_model": "zero",
        },
        files={
            "file": (
                "mixed_library.smi",
                io.BytesIO(b"CCO ethanol\nC1CC invalid_ring\n"),
                "text/plain",
            ),
        },
    )

    assert response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        summary = json.loads(zip_file.read("summary.json").decode("utf-8"))

    assert summary["total"] == 2
    assert summary["successful"] == 1
    assert summary["failed"] == 1
