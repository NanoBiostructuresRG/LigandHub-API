import io
from pathlib import Path
import uuid

from fastapi.testclient import TestClient

import app as app_module
import docking_io
from app import app


client = TestClient(app)


def test_convert_pdbqt_to_sdf_endpoint_returns_sdf_from_prepared_ethanol(monkeypatch, workspace_tempdir):
    fixture_path = Path(__file__).parent / "fixtures" / "ethanol.smi"
    temp_root = workspace_tempdir(app_module, "convert_pdbqt_to_sdf_endpoint")

    def workspace_named_temporary_file(mode="w+", suffix="", encoding=None, **kwargs):
        output_path = temp_root / f"tmp_{uuid.uuid4().hex}{suffix}"
        return output_path.open(mode=mode, encoding=encoding)

    monkeypatch.setattr(docking_io.tempfile, "NamedTemporaryFile", workspace_named_temporary_file)

    with fixture_path.open("rb") as ligand_file:
        prepare_response = client.post(
            "/prepare_ligand",
            data={
                "filename": "ethanol",
                "charge_model": "zero",
            },
            files={
                "file": ("ethanol.smi", ligand_file, "text/plain"),
            },
        )

    assert prepare_response.status_code == 200

    convert_response = client.post(
        "/convert_pdbqt_to_sdf",
        data={
            "filename": "ethanol",
        },
        files={
            "file": ("ethanol.pdbqt", io.BytesIO(prepare_response.content), "text/plain"),
        },
    )

    assert convert_response.status_code == 200
    assert ".sdf" in convert_response.headers["Content-Disposition"]

    sdf_text = convert_response.text
    assert "M  END" in sdf_text
    assert "$$$$" in sdf_text
