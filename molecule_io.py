import os

from fastapi import HTTPException
from rdkit import Chem

from validation import full_validation, validate_loaded_molecule


def load_molecule_from_file(input_path: str, original_filename: str):
    ext = os.path.splitext(original_filename)[1].lower()

    if ext in {".smi", ".smiles", ".txt"}:
        with open(input_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if not lines:
            raise HTTPException(status_code=400, detail="Empty SMILES file")

        smiles_str = lines[0].split()[0]
        mol, errors, warnings = full_validation(smiles_str)
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
        return mol, warnings

    if ext == ".sdf":
        supplier = Chem.SDMolSupplier(input_path, sanitize=False, removeHs=False)
        mol = next((m for m in supplier if m is not None), None)
        if mol is None:
            raise HTTPException(status_code=400, detail="Could not read molecule from SDF")
        return mol, validate_loaded_molecule(mol)

    if ext == ".mol2":
        mol = Chem.MolFromMol2File(input_path, sanitize=False, removeHs=False)
        if mol is None:
            raise HTTPException(status_code=400, detail="Could not read molecule from MOL2")
        return mol, validate_loaded_molecule(mol)

    if ext == ".pdb":
        mol = Chem.MolFromPDBFile(input_path, sanitize=False, removeHs=False)
        if mol is None:
            raise HTTPException(status_code=400, detail="Could not read molecule from PDB")
        return mol, validate_loaded_molecule(mol)

    raise HTTPException(
        status_code=400,
        detail="Unsupported file format. Use SDF, MOL2, PDB, or a SMILES text file."
    )
