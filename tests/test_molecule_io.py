from pathlib import Path

import pytest
from fastapi import HTTPException

from molecule_io import load_molecule_from_file


def output_path(name: str) -> Path:
    root = Path("tmp_test") / "molecule_io"
    root.mkdir(parents=True, exist_ok=True)
    return root / name


def test_load_molecule_from_file_reads_smiles_fixture():
    mol, warnings = load_molecule_from_file("tests/fixtures/ethanol.smi", "ethanol.smi")

    assert mol is not None
    assert mol.GetNumAtoms() == 3
    assert warnings == []


def test_load_molecule_from_file_reads_sdf_fixture():
    mol, warnings = load_molecule_from_file("tests/fixtures/ethanol.sdf", "ethanol.sdf")

    assert mol is not None
    assert mol.GetNumAtoms() == 9
    assert mol.GetNumConformers() == 1
    assert warnings == []


def test_load_molecule_from_file_reads_pdb_fixture():
    mol, warnings = load_molecule_from_file("tests/fixtures/ethanol.pdb", "ethanol.pdb")

    assert mol is not None
    assert mol.GetNumAtoms() == 9
    assert mol.GetNumConformers() == 1
    assert warnings == []


def test_load_molecule_from_file_reads_mol2_fixture():
    mol, warnings = load_molecule_from_file("tests/fixtures/ethanol.mol2", "ethanol.mol2")

    assert mol is not None
    assert mol.GetNumAtoms() == 9
    assert mol.GetNumConformers() == 1
    assert warnings == []


def test_load_molecule_from_file_reads_mol2_with_indented_section_headers():
    mol, warnings = load_molecule_from_file(
        "tests/fixtures/benzene_leading_space_headers.mol2",
        "benzene_leading_space_headers.mol2",
    )

    assert mol is not None
    assert mol.GetNumAtoms() == 12
    assert mol.GetNumConformers() == 1
    assert warnings == []


def test_load_molecule_from_file_rejects_empty_smiles_file():
    empty_file = output_path("empty.smi")
    empty_file.write_text("", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        load_molecule_from_file(str(empty_file), "empty.smi")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Empty SMILES file"


def test_load_molecule_from_file_rejects_invalid_sdf_file():
    invalid_file = output_path("invalid.sdf")
    invalid_file.write_text("not an sdf\n", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        load_molecule_from_file(str(invalid_file), "invalid.sdf")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Could not read molecule from SDF"


def test_load_molecule_from_file_rejects_empty_sdf_file():
    empty_file = output_path("empty.sdf")
    empty_file.write_text("", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        load_molecule_from_file(str(empty_file), "empty.sdf")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Could not read molecule from SDF"


def test_load_molecule_from_file_rejects_sdf_without_valid_molecules():
    invalid_file = output_path("no_valid_molecules.sdf")
    invalid_file.write_text("$$$$\n", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        load_molecule_from_file(str(invalid_file), "no_valid_molecules.sdf")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Could not read molecule from SDF"


def test_load_molecule_from_file_rejects_invalid_pdb_file():
    invalid_file = output_path("invalid.pdb")
    invalid_file.write_text("not a pdb\n", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        load_molecule_from_file(str(invalid_file), "invalid.pdb")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Could not read molecule from PDB"


def test_load_molecule_from_file_rejects_invalid_mol2_file():
    invalid_file = output_path("invalid.mol2")
    invalid_file.write_text("not a mol2\n", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        load_molecule_from_file(str(invalid_file), "invalid.mol2")

    assert exc_info.value.status_code == 400
    assert "Could not read molecule from MOL2" in exc_info.value.detail


def test_load_molecule_from_file_reports_gaff_like_mol2_atom_types():
    with pytest.raises(HTTPException) as exc_info:
        load_molecule_from_file(
            "tests/fixtures/benzene_gaff_like_atom_types.mol2",
            "benzene_gaff_like_atom_types.mol2",
        )

    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert "Could not read molecule from MOL2" in detail
    assert "ca" in detail
    assert "ha" in detail
    assert "C.ar" in detail


def test_load_molecule_from_file_rejects_supported_extension_with_wrong_content():
    invalid_file = output_path("wrong_content.txt")
    invalid_file.write_text("not_a_smiles ligand\n", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        load_molecule_from_file(str(invalid_file), "wrong_content.txt")

    assert exc_info.value.status_code == 400
    assert "Validation failed" in exc_info.value.detail["message"]
