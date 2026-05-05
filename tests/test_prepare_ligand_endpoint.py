from pathlib import Path

from fastapi.testclient import TestClient

import app as app_module
from app import app


client = TestClient(app)


def test_prepare_ligand_endpoint_returns_pdbqt_for_ethanol_smiles(workspace_tempdir):
    fixture_path = Path(__file__).parent / "fixtures" / "ethanol.smi"
    workspace_tempdir(app_module, "prepare_ligand_endpoint")

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
