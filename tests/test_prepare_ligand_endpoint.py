from pathlib import Path
import shutil
import uuid

from fastapi.testclient import TestClient

import app as app_module
from app import app


client = TestClient(app)


def test_prepare_ligand_endpoint_returns_pdbqt_for_ethanol_smiles(monkeypatch):
    fixture_path = Path(__file__).parent / "fixtures" / "ethanol.smi"
    temp_root = Path("tmp_test") / "prepare_ligand_endpoint"
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
            "/prepare_ligand",
            data={
                "filename": "ethanol",
                "charge_model": "zero",
            },
            files={
                "file": ("ethanol.smi", ligand_file, "text/plain"),
            },
        )

    assert response.status_code == 200
    assert ".pdbqt" in response.headers["Content-Disposition"]

    pdbqt_text = response.text
    pdbqt_lines = pdbqt_text.splitlines()

    assert any(line.startswith(("ATOM", "HETATM")) for line in pdbqt_lines)
    assert "ROOT" in pdbqt_text
    assert "ENDROOT" in pdbqt_text
    assert "TORSDOF" in pdbqt_text
