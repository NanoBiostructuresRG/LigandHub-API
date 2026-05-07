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


def test_prepare_ligand_endpoint_returns_pdbqt_for_ethanol_sdf(workspace_tempdir):
    fixture_path = Path(__file__).parent / "fixtures" / "ethanol.sdf"
    workspace_tempdir(app_module, "prepare_ligand_endpoint_sdf")

    with fixture_path.open("rb") as ligand_file:
        response = client.post(
            "/prepare_ligand",
            data={
                "filename": "ethanol_sdf",
                "charge_model": "zero",
            },
            files={
                "file": ("ethanol.sdf", ligand_file, "chemical/x-mdl-sdfile"),
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


def test_prepare_ligand_endpoint_returns_pdbqt_for_ethanol_mol2(workspace_tempdir):
    fixture_path = Path(__file__).parent / "fixtures" / "ethanol.mol2"
    workspace_tempdir(app_module, "prepare_ligand_endpoint_mol2")

    with fixture_path.open("rb") as ligand_file:
        response = client.post(
            "/prepare_ligand",
            data={
                "filename": "ethanol_mol2",
                "charge_model": "zero",
            },
            files={
                "file": ("ethanol.mol2", ligand_file, "chemical/x-mol2"),
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


def test_prepare_ligand_endpoint_accepts_mol2_with_indented_section_headers(workspace_tempdir):
    fixture_path = Path(__file__).parent / "fixtures" / "benzene_leading_space_headers.mol2"
    workspace_tempdir(app_module, "prepare_ligand_endpoint_indented_mol2")

    with fixture_path.open("rb") as ligand_file:
        response = client.post(
            "/prepare_ligand",
            data={
                "filename": "benzene_indented_mol2",
                "charge_model": "zero",
            },
            files={
                "file": ("benzene_leading_space_headers.mol2", ligand_file, "chemical/x-mol2"),
            },
        )

    assert response.status_code == 200
    assert ".pdbqt" in response.headers["Content-Disposition"]

    pdbqt_text = response.text
    pdbqt_lines = pdbqt_text.splitlines()

    assert "REMARK SMILES" in pdbqt_text
    assert any(line.startswith(("ATOM", "HETATM")) for line in pdbqt_lines)
    assert "ROOT" in pdbqt_text
    assert "ENDROOT" in pdbqt_text
    assert "TORSDOF" in pdbqt_text


def test_prepare_ligand_endpoint_reports_gaff_like_mol2_atom_types(workspace_tempdir):
    fixture_path = Path(__file__).parent / "fixtures" / "benzene_gaff_like_atom_types.mol2"
    workspace_tempdir(app_module, "prepare_ligand_endpoint_gaff_like_mol2")

    with fixture_path.open("rb") as ligand_file:
        response = client.post(
            "/prepare_ligand",
            data={
                "filename": "benzene_gaff_like_mol2",
                "charge_model": "zero",
            },
            files={
                "file": ("benzene_gaff_like_atom_types.mol2", ligand_file, "chemical/x-mol2"),
            },
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Could not read molecule from MOL2" in detail
    assert "ca" in detail
    assert "ha" in detail
    assert response.status_code != 500
