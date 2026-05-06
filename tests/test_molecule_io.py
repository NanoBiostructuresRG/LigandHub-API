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
