from rdkit import Chem

from validation import (
    build_atom_validation_error,
    full_validation,
    get_valence_from_message,
    validate_molecule_structure,
    validate_smiles,
)


def test_validate_smiles_accepts_valid_smiles():
    mol, error = validate_smiles("CCO")

    assert mol is not None
    assert error is None


def test_validate_smiles_rejects_empty_input():
    mol, error = validate_smiles("   ")

    assert mol is None
    assert error == {"type": "smiles_error", "message": "SMILES string is empty"}


def test_validate_smiles_reports_invalid_syntax():
    mol, error = validate_smiles("C1CC")

    assert mol is None
    assert error["type"] == "smiles_error"
    assert "Invalid SMILES syntax" in error["message"]


def test_get_valence_from_message_handles_known_message_shapes():
    assert get_valence_from_message("Explicit valence for atom # 1 C, 5, is greater than permitted") == 5
    assert get_valence_from_message("atom has valence 7") == 7
    assert get_valence_from_message("no valence data here") is None


def test_build_atom_validation_error_uses_atom_metadata():
    mol = Chem.MolFromSmiles("CCO")
    atom = mol.GetAtomWithIdx(2)

    error = build_atom_validation_error(atom, "custom message")

    assert error["type"] == "valence_error"
    assert error["atom"] == 3
    assert error["element"] == "O"
    assert error["max_valence"] == 2
    assert "typical max 2" in error["message"]


def test_validate_molecule_structure_warns_for_metal_atom():
    mol = Chem.MolFromSmiles("[Na+]")

    errors, warnings = validate_molecule_structure(mol)

    assert errors == []
    assert any(warning["type"] == "metal_detected" for warning in warnings)


def test_full_validation_returns_errors_for_invalid_smiles():
    mol, errors, warnings = full_validation("")

    assert mol is None
    assert errors[0]["type"] == "smiles_error"
    assert warnings == []
