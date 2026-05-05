import io
import json
import zipfile

from fastapi.testclient import TestClient

import app as app_module
from app import app


client = TestClient(app)


def test_prepare_ligand_rejects_empty_upload(workspace_tempdir):
    workspace_tempdir(app_module, "prepare_ligand_empty_upload")

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


def test_prepare_ligand_rejects_invalid_charge_model():
    response = client.post(
        "/prepare_ligand",
        data={
            "filename": "ethanol",
            "charge_model": "bad-model",
        },
        files={
            "file": ("ethanol.smi", io.BytesIO(b"CCO ethanol\n"), "text/plain"),
        },
    )

    assert response.status_code == 400
    assert "Invalid 'charge_model'" in response.json()["detail"]


def test_prepare_ligand_rejects_minimization_max_iters_out_of_range():
    response = client.post(
        "/prepare_ligand",
        data={
            "filename": "ethanol",
            "charge_model": "zero",
            "minimization_max_iters": "0",
        },
        files={
            "file": ("ethanol.smi", io.BytesIO(b"CCO ethanol\n"), "text/plain"),
        },
    )

    assert response.status_code == 400
    assert "'minimization_max_iters' must be between 1 and 2000" == response.json()["detail"]


def test_prepare_ligand_rejects_invalid_extension(workspace_tempdir):
    workspace_tempdir(app_module, "prepare_ligand_invalid_extension")

    response = client.post(
        "/prepare_ligand",
        data={
            "filename": "ethanol",
            "charge_model": "zero",
        },
        files={
            "file": ("ethanol.xyz", io.BytesIO(b"CCO ethanol\n"), "text/plain"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file format. Use SDF, MOL2, PDB, or a SMILES text file."


def test_prepare_ligand_rejects_upload_over_size_limit(monkeypatch, workspace_tempdir):
    workspace_tempdir(app_module, "prepare_ligand_upload_limit")
    monkeypatch.setattr(app_module, "MAX_UPLOAD_SIZE_BYTES", 5)

    response = client.post(
        "/prepare_ligand",
        data={
            "filename": "ethanol",
            "charge_model": "zero",
        },
        files={
            "file": ("ethanol.smi", io.BytesIO(b"CCO ethanol\n"), "text/plain"),
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"]["message"] == "Uploaded file exceeds the 5 byte limit"


def test_prepare_ligand_batch_rejects_empty_upload(workspace_tempdir):
    workspace_tempdir(app_module, "prepare_ligand_batch_empty_upload")

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


def test_prepare_ligand_batch_rejects_invalid_extension():
    response = client.post(
        "/prepare_ligand_batch",
        data={
            "filename": "library",
            "charge_model": "zero",
        },
        files={
            "file": ("library.csv", io.BytesIO(b"CCO ethanol\n"), "text/csv"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Batch processing requires a .smi, .smiles, or .txt SMILES library file"


def test_prepare_ligand_batch_rejects_upload_over_size_limit(monkeypatch, workspace_tempdir):
    workspace_tempdir(app_module, "prepare_ligand_batch_upload_limit")
    monkeypatch.setattr(app_module, "MAX_BATCH_UPLOAD_SIZE_BYTES", 5)

    response = client.post(
        "/prepare_ligand_batch",
        data={
            "filename": "library",
            "charge_model": "zero",
        },
        files={
            "file": ("library.smi", io.BytesIO(b"CCO ethanol\n"), "text/plain"),
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"]["message"] == "Uploaded file exceeds the 5 byte limit"


def test_prepare_ligand_batch_reports_failed_count_for_invalid_smiles(workspace_tempdir):
    workspace_tempdir(app_module, "prepare_ligand_batch_invalid_smiles")

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


def test_prepare_ligand_batch_rejects_when_all_ligands_fail(workspace_tempdir):
    workspace_tempdir(app_module, "prepare_ligand_batch_all_failed")

    response = client.post(
        "/prepare_ligand_batch",
        data={
            "filename": "invalid_library",
            "charge_model": "zero",
        },
        files={
            "file": (
                "invalid_library.smi",
                io.BytesIO(b"C1CC bad_ring\nnot_smiles syntax\n"),
                "text/plain",
            ),
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["message"] == "No PDBQT files could be generated from the uploaded library"
    assert detail["summary"]["total"] == 2
    assert detail["summary"]["successful"] == 0
    assert detail["summary"]["failed"] == 2


def test_convert_pdbqt_to_sdf_rejects_invalid_extension():
    response = client.post(
        "/convert_pdbqt_to_sdf",
        data={
            "filename": "docked",
        },
        files={
            "file": ("docked.sdf", io.BytesIO(b"not pdbqt"), "text/plain"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported docking results format. Use PDBQT or DLG files."
