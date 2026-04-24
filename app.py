"""
LigandHub API - Backend for ligand preparation using Meeko
Endpoint: /prepare_ligand
"""

import os
import re
import tempfile
import logging

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import uvicorn

from meeko import MoleculePreparation, PDBQTMolecule, PDBQTWriterLegacy, RDKitMolCreate
from rdkit import Chem
from rdkit.Chem import AllChem

app = FastAPI(
    title="LigandHub API",
    description="Ligand preparation for AutoDock Vina using Meeko"
)

logger = logging.getLogger(__name__)
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
SUPPORTED_CHARGE_MODELS = {"gasteiger", "nagl", "espaloma", "zero"}

# Replace this with the real URL of your frontend on GitHub Pages
ALLOWED_ORIGINS = [
    "https://nanobiostructuresrg.github.io",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://nanobiostructuresrg\.github\.io",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "LigandHub API is running", "status": "online"}


@app.get("/health")
async def health():
    return {"status": "ok"}


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w.-]+", "_", name).strip("._")
    return name or "ligand"


async def save_upload_file(upload_file: UploadFile, destination_path: str, max_size_bytes: int) -> None:
    total_size = 0
    chunk_size = 1024 * 1024

    with open(destination_path, "wb") as destination:
        while True:
            chunk = await upload_file.read(chunk_size)
            if not chunk:
                break

            total_size += len(chunk)
            if total_size > max_size_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Uploaded file exceeds the {max_size_bytes} byte limit"
                )

            destination.write(chunk)

    if total_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")


def load_molecule_from_file(input_path: str, original_filename: str):
    ext = os.path.splitext(original_filename)[1].lower()

    if ext in {".smi", ".smiles", ".txt"}:
        with open(input_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if not lines:
            raise HTTPException(status_code=400, detail="Empty SMILES file")

        smiles_str = lines[0].split()[0]
        mol = Chem.MolFromSmiles(smiles_str)
        if mol is None:
            raise HTTPException(status_code=400, detail="Invalid SMILES string")
        return mol

    if ext == ".sdf":
        supplier = Chem.SDMolSupplier(input_path, removeHs=False)
        mol = next((m for m in supplier if m is not None), None)
        if mol is None:
            raise HTTPException(status_code=400, detail="Could not read molecule from SDF")
        return mol

    if ext == ".mol2":
        mol = Chem.MolFromMol2File(input_path, removeHs=False)
        if mol is None:
            raise HTTPException(status_code=400, detail="Could not read molecule from MOL2")
        return mol

    if ext == ".pdb":
        mol = Chem.MolFromPDBFile(input_path, removeHs=False)
        if mol is None:
            raise HTTPException(status_code=400, detail="Could not read molecule from PDB")
        return mol

    raise HTTPException(
        status_code=400,
        detail="Unsupported file format. Use SDF, MOL2, PDB, or a SMILES text file."
    )


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


def ensure_3d_and_hydrogens(mol):
    # Add Hs explicit; addCoords helps preserve coordinates when they exist
    mol = Chem.AddHs(mol, addCoords=True)

    needs_3d = (
        mol.GetNumConformers() == 0 or
        not mol.GetConformer().Is3D()
    )

    if needs_3d:
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        embed_status = AllChem.EmbedMolecule(mol, params)

        if embed_status != 0:
            raise HTTPException(status_code=400, detail="RDKit could not generate 3D coordinates")

        mmff_props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
        if mmff_props is not None:
            AllChem.MMFFOptimizeMolecule(mol)
        else:
            AllChem.UFFOptimizeMolecule(mol)

    return mol


@app.post("/prepare_ligand")
async def prepare_ligand(
    file: UploadFile = File(...),
    filename: str = Form("ligand"),
    output_format: str = Form("pdbqt"),
    merge_h: bool = Form(True),
    charge_model: str = Form("gasteiger"),
):
    """
    Prepare ligand for AutoDock Vina using Meeko.

    Notes:
    - `merge_h=True` merges hydrogens using the default behavior.
    - `merge_h=False` keeps hydrogens separate.
    - `charge_model` supports: gasteiger, nagl, espaloma, zero.
    """

    if output_format != "pdbqt":
        raise HTTPException(
            status_code=400,
            detail="Currently only 'pdbqt' output is implemented"
        )

    charge_model = charge_model.strip().lower()
    if charge_model not in SUPPORTED_CHARGE_MODELS:
        raise HTTPException(
            status_code=400,
            detail="Invalid 'charge_model'. Use one of: gasteiger, nagl, espaloma, zero"
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="No input filename provided")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, sanitize_filename(file.filename))
            await save_upload_file(file, input_path, MAX_UPLOAD_SIZE_BYTES)

            mol = load_molecule_from_file(input_path, file.filename)
            mol = ensure_3d_and_hydrogens(mol)

            merge_these = ("H",) if merge_h else ()
            preparator = MoleculePreparation(
                merge_these_atom_types=merge_these,
                charge_model=charge_model,
            )

            mol_setups = preparator.prepare(mol)

            if not mol_setups:
                raise HTTPException(status_code=400, detail="Meeko could not prepare the ligand")

            pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(mol_setups[0])

            if not is_ok:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error generating PDBQT: {error_msg}"
                )

            base_name = sanitize_filename(os.path.splitext(filename or file.filename)[0])
            output_filename = f"{base_name}_prepared.pdbqt"

            return Response(
                content=pdbqt_string,
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{output_filename}"'
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected server error while preparing ligand")
        raise HTTPException(status_code=500, detail="Unexpected server error")


@app.post("/convert_pdbqt_to_sdf")
async def convert_pdbqt_to_sdf(
    file: UploadFile = File(...),
    filename: str = Form("docked_results"),
):
    """
    Convert docking results from PDBQT or DLG back to SDF using Meeko's export logic.

    Notes:
    - PDBQT results are typically produced by AutoDock Vina.
    - DLG results are typically produced by AutoDock-GPU.
    - Meeko reconstructs bond orders using the REMARK metadata preserved in docking outputs.
    """

    if not file.filename:
        raise HTTPException(status_code=400, detail="No input filename provided")

    try:
        docking_format = detect_docking_results_format(file.filename)

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, sanitize_filename(file.filename))
            await save_upload_file(file, input_path, MAX_UPLOAD_SIZE_BYTES)

            sdf_string = export_docking_results_to_sdf_string(input_path, docking_format)
            base_name = sanitize_filename(os.path.splitext(filename or file.filename)[0])
            output_filename = f"{base_name}_docked.sdf"

            return Response(
                content=sdf_string,
                media_type="chemical/x-mdl-sdfile; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{output_filename}"'
                },
            )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected server error while converting docking results")
        raise HTTPException(status_code=500, detail="Unexpected server error")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
