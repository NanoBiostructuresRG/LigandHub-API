from fastapi import HTTPException
from rdkit import Chem

from file_io import validate_file_extension
from validation import full_validation, validate_loaded_molecule


SUSPICIOUS_MOL2_ATOM_TYPES = {"ca", "ha"}


def normalize_mol2_section_headers(mol2_text: str) -> str:
    lines = []
    for line in mol2_text.splitlines(keepends=True):
        stripped_line = line.lstrip()
        if stripped_line.startswith("@<TRIPOS>"):
            lines.append(stripped_line)
        else:
            lines.append(line)

    return "".join(lines)


def extract_mol2_atom_types(mol2_text: str) -> set[str]:
    atom_types = set()
    in_atom_section = False

    for raw_line in mol2_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("@<TRIPOS>"):
            in_atom_section = line == "@<TRIPOS>ATOM"
            continue

        if in_atom_section:
            parts = line.split()
            if len(parts) >= 6:
                atom_types.add(parts[5])

    return atom_types


def build_mol2_read_error_detail(mol2_text: str) -> str:
    detail = (
        "Could not read molecule from MOL2. The file may use unsupported MOL2 atom "
        "types or non-standard section formatting. Expected Sybyl-like atom types "
        "such as C.ar, C.3, N.am, O.2, or H."
    )

    suspicious_types = sorted(
        atom_type for atom_type in extract_mol2_atom_types(mol2_text)
        if atom_type.lower() in SUSPICIOUS_MOL2_ATOM_TYPES
    )
    if suspicious_types:
        detail = (
            f"{detail} Detected suspicious atom types: {', '.join(suspicious_types)}. "
            "For GAFF/Amber-like MOL2 files, convert atom types such as ca -> C.ar "
            "and ha -> H, or upload SDF/SMILES instead."
        )

    return detail


def load_molecule_from_file(input_path: str, original_filename: str):
    ext = validate_file_extension(
        original_filename,
        {".smi", ".smiles", ".txt", ".sdf", ".mol2", ".pdb"},
        "Unsupported file format. Use SDF, MOL2, PDB, or a SMILES text file.",
    )

    if ext in {".smi", ".smiles", ".txt"}:
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="SMILES text files must be valid UTF-8 text",
            )
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
        try:
            supplier = Chem.SDMolSupplier(input_path, sanitize=False, removeHs=False)
        except OSError:
            raise HTTPException(status_code=400, detail="Could not read molecule from SDF")
        mol = next((m for m in supplier if m is not None), None)
        if mol is None:
            raise HTTPException(status_code=400, detail="Could not read molecule from SDF")
        return mol, validate_loaded_molecule(mol)

    if ext == ".mol2":
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                mol2_text = f.read()
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="MOL2 files must be valid UTF-8 text",
            )

        mol2_text = normalize_mol2_section_headers(mol2_text)
        mol = Chem.MolFromMol2Block(mol2_text, sanitize=False, removeHs=False)
        if mol is None:
            raise HTTPException(
                status_code=400,
                detail=build_mol2_read_error_detail(mol2_text),
            )
        return mol, validate_loaded_molecule(mol)

    if ext == ".pdb":
        mol = Chem.MolFromPDBFile(input_path, sanitize=False, removeHs=False)
        if mol is None:
            raise HTTPException(status_code=400, detail="Could not read molecule from PDB")
        return mol, validate_loaded_molecule(mol)
