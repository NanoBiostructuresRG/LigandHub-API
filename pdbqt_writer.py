from fastapi import HTTPException
from meeko import MoleculePreparation, PDBQTWriterLegacy


def prepare_molecule_setups(mol, merge_h: bool, charge_model: str, empty_error_detail: str):
    merge_these = ("H",) if merge_h else ()
    preparator = MoleculePreparation(
        merge_these_atom_types=merge_these,
        charge_model=charge_model,
    )

    mol_setups = preparator.prepare(mol)

    if not mol_setups:
        raise HTTPException(status_code=400, detail=empty_error_detail)

    return mol_setups


def write_pdbqt_string(mol_setup) -> str:
    pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(mol_setup)

    if not is_ok:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating PDBQT: {error_msg}",
        )

    return pdbqt_string
