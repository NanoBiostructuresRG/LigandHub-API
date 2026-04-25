import re

from fastapi import HTTPException
from rdkit import Chem, RDLogger
from rdkit.Chem.rdchem import AtomValenceException

from config import COMMON_ELEMENTS, METALS


def format_atom_label(atom) -> str:
    return f"{atom.GetSymbol()} atom #{atom.GetIdx() + 1}"


def get_exception_atom_index(exc) -> int:
    if hasattr(exc, "GetAtomIdx"):
        return exc.GetAtomIdx()

    match = re.search(r"atom #\s*(\d+)", str(exc))
    if match:
        return int(match.group(1))

    return -1


def get_atom_total_valence(atom) -> int:
    try:
        return atom.GetTotalValence()
    except RuntimeError:
        return atom.GetExplicitValence()


def get_valence_from_message(message: str) -> int | None:
    match = re.search(r",\s*(\d+),\s*is greater than permitted", message)
    if match:
        return int(match.group(1))

    match = re.search(r"valence\s+(\d+)", message, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


def build_atom_validation_error(atom, message: str | None = None) -> dict:
    total_valence = get_valence_from_message(message or "") or get_atom_total_valence(atom)
    atomic_num = atom.GetAtomicNum()
    max_valence = {
        1: 1,
        5: 3,
        6: 4,
        7: 4,
        8: 2,
        9: 1,
        15: 5,
        16: 6,
        17: 1,
        35: 1,
        53: 1,
    }.get(atomic_num)

    detail = message or f"{format_atom_label(atom)} has valence {total_valence}"
    if max_valence is not None:
        detail = f"{format_atom_label(atom)} has valence {total_valence} (typical max {max_valence})"

    return {
        "type": "valence_error",
        "atom": atom.GetIdx() + 1,
        "element": atom.GetSymbol(),
        "valence": total_valence,
        "max_valence": max_valence,
        "message": detail,
    }


def validate_smiles(smiles: str):
    smiles = smiles.strip()
    if not smiles:
        return None, {"type": "smiles_error", "message": "SMILES string is empty"}

    RDLogger.DisableLog("rdApp.error")
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            return mol, None

        unsanitized_mol = Chem.MolFromSmiles(smiles, sanitize=False)
        if unsanitized_mol is None:
            return None, {
                "type": "smiles_error",
                "message": "Invalid SMILES syntax - check parentheses, brackets, and ring closures",
            }
    finally:
        RDLogger.EnableLog("rdApp.error")

    RDLogger.DisableLog("rdApp.error")
    try:
        Chem.SanitizeMol(unsanitized_mol)
        return unsanitized_mol, None
    except AtomValenceException as exc:
        atom_index = get_exception_atom_index(exc)
        if atom_index >= 0:
            atom = unsanitized_mol.GetAtomWithIdx(atom_index)
            return None, build_atom_validation_error(atom, str(exc))
        return None, {"type": "valence_error", "message": str(exc)}
    except Exception as exc:
        return None, {
            "type": "structure_error",
            "message": f"RDKit could not sanitize the molecule: {exc}",
        }
    finally:
        RDLogger.EnableLog("rdApp.error")


def validate_molecule_structure(mol):
    errors = []
    warnings = []

    RDLogger.DisableLog("rdApp.error")
    try:
        Chem.SanitizeMol(mol)
    except AtomValenceException as exc:
        atom_index = get_exception_atom_index(exc)
        if atom_index >= 0:
            atom = mol.GetAtomWithIdx(atom_index)
            errors.append(build_atom_validation_error(atom, str(exc)))
        else:
            errors.append({"type": "valence_error", "message": str(exc)})
    except Exception as exc:
        errors.append({
            "type": "structure_error",
            "message": f"RDKit could not sanitize the molecule: {exc}",
        })
    finally:
        RDLogger.EnableLog("rdApp.error")

    if errors:
        return errors, warnings

    for atom in mol.GetAtoms():
        element = atom.GetSymbol()
        idx = atom.GetIdx() + 1

        if element not in COMMON_ELEMENTS:
            warnings.append({
                "type": "unknown_element",
                "atom": idx,
                "element": element,
                "message": f"Unknown or unusual element '{element}' at atom #{idx}",
            })

        if element in METALS:
            warnings.append({
                "type": "metal_detected",
                "atom": idx,
                "element": element,
                "message": f"Metal atom {element} at atom #{idx} - verify formal charges",
            })

    total_charge = Chem.GetFormalCharge(mol)
    if abs(total_charge) > 3:
        warnings.append({
            "type": "high_charge",
            "charge": total_charge,
            "message": f"High net charge ({total_charge}) - verify molecule",
        })

    return errors, warnings


def full_validation(smiles: str):
    mol, error = validate_smiles(smiles)
    if error:
        return None, [error], []

    errors, warnings = validate_molecule_structure(mol)
    return mol, errors, warnings


def validate_loaded_molecule(mol):
    errors, warnings = validate_molecule_structure(mol)
    if errors:
        error_details = "; ".join(error["message"] for error in errors)
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Validation failed: {error_details}",
                "errors": errors,
                "warnings": warnings,
            },
        )

    return warnings
