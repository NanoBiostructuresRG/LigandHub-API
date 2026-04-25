import os
import tempfile

from fastapi import HTTPException
from meeko import PDBQTMolecule, RDKitMolCreate
from rdkit import Chem


def detect_docking_results_format(original_filename: str) -> str:
    normalized_name = original_filename.lower()

    if normalized_name.endswith(".pdbqt") or normalized_name.endswith(".pdbqt.gz"):
        return "pdbqt"

    if normalized_name.endswith(".dlg") or normalized_name.endswith(".dlg.gz"):
        return "dlg"

    raise HTTPException(
        status_code=400,
        detail="Unsupported docking results format. Use PDBQT or DLG files."
    )


def export_docking_results_to_sdf_string(input_path: str, docking_format: str) -> str:
    pdbqt_mol = PDBQTMolecule.from_file(
        input_path,
        is_dlg=(docking_format == "dlg"),
        skip_typing=True,
    )
    rdkit_mol_list = RDKitMolCreate.from_pdbqt_mol(pdbqt_mol)
    valid_mols = [mol for mol in rdkit_mol_list if mol is not None]

    if not valid_mols:
        raise HTTPException(
            status_code=400,
            detail="Meeko could not reconstruct any molecule from the docking results"
        )

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".sdf", delete=False, encoding="utf-8") as tmp_sdf:
        output_path = tmp_sdf.name

    try:
        writer = Chem.SDWriter(output_path)
        for mol in valid_mols:
            writer.write(mol)
        writer.close()

        with open(output_path, "r", encoding="utf-8") as sdf_file:
            return sdf_file.read()
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)
