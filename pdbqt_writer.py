from fastapi import HTTPException
from meeko import PDBQTWriterLegacy


def write_pdbqt_string(mol_setup) -> str:
    pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(mol_setup)

    if not is_ok:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating PDBQT: {error_msg}",
        )

    return pdbqt_string
