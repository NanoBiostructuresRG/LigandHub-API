import io
from pathlib import Path
import shutil
import uuid

from fastapi.testclient import TestClient

import app as app_module
import docking_io
from app import app


client = TestClient(app)


def test_convert_pdbqt_to_sdf_endpoint_returns_sdf_from_prepared_ethanol(monkeypatch):
    fixture_path = Path(__file__).parent / "fixtures" / "ethanol.smi"
    temp_root = Path("tmp_test") / "convert_pdbqt_to_sdf_endpoint"
    temp_root.mkdir(parents=True, exist_ok=True)

    class WorkspaceTemporaryDirectory:
        def __init__(self):
            self.name = str(temp_root / f"tmp_{uuid.uuid4().hex}")

        def __enter__(self):
            Path(self.name).mkdir(parents=True, exist_ok=False)
            return self.name

        def __exit__(self, exc_type, exc, traceback):
            shutil.rmtree(self.name, ignore_errors=True)

    def workspace_named_temporary_file(mode="w+", suffix="", encoding=None, **kwargs):
        output_path = temp_root / f"tmp_{uuid.uuid4().hex}{suffix}"
        return output_path.open(mode=mode, encoding=encoding)

    monkeypatch.setattr(app_module.tempfile, "TemporaryDirectory", WorkspaceTemporaryDirectory)
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
