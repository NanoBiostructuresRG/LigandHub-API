"""
LigandHub API - Backend for ligand preparation using Meeko
Endpoint: /prepare_ligand
"""

import os
import re
import tempfile
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import uvicorn

from meeko import MoleculePreparation, PDBQTWriterLegacy
from rdkit import Chem
from rdkit.Chem import AllChem

app = FastAPI(
    title="LigandHub API",
    description="Ligand preparation for AutoDock Vina using Meeko"
)

# Reemplaza esto por la URL real de tu frontend en GitHub Pages
ALLOWED_ORIGINS = [
    "https://TU-USUARIO.github.io",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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


def ensure_3d_and_hydrogens(mol):
    # Añadir Hs explícitos; addCoords ayuda a preservar coords cuando existan
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
    ph: float = Form(7.4),  # Se acepta, pero por ahora no modifica protonación
    output_format: str = Form("pdbqt"),
):
    """
    Prepare ligand for AutoDock Vina using Meeko.

    Nota:
    - Meeko no asigna protonación automáticamente.
    - El parámetro `ph` se recibe por compatibilidad de frontend, pero no se aplica.
    """

    if output_format != "pdbqt":
        raise HTTPException(
            status_code=400,
            detail="Currently only 'pdbqt' output is implemented"
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="No input filename provided")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, sanitize_filename(file.filename))

            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")

            with open(input_path, "wb") as f:
                f.write(content)

            mol = load_molecule_from_file(input_path, file.filename)
            mol = ensure_3d_and_hydrogens(mol)

            preparator = MoleculePreparation()
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
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(e)}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)