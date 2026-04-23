"""
LigandHub API - Backend for ligand preparation using Meeko
Endpoint: /prepare_ligand
"""

import os
import tempfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Meeko imports (usando la API correcta)
from meeko import MoleculePreparation, PDBQTWriterLegacy
from rdkit import Chem
from rdkit.Chem import AllChem

app = FastAPI(title="LigandHub API", description="Ligand preparation for AutoDock Vina using Meeko")

# Enable CORS for frontend (GitHub Pages)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

@app.post("/prepare_ligand")
async def prepare_ligand(
    file: UploadFile = File(...),
    ph: float = Form(7.4),
    output_format: str = Form("pdbqt"),
    filename: str = Form("ligand")
):
    """
    Prepare ligand for AutoDock Vina using Meeko
    """
    # Validar formato de salida
    if output_format not in ["pdbqt", "pdb", "both"]:
        raise HTTPException(status_code=400, detail="Invalid output format")

    # Crear directorio temporal
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Guardar archivo subido temporalmente
            input_path = os.path.join(tmpdir, file.filename)
            content = await file.read()
            with open(input_path, "wb") as f:
                f.write(content)

            # 1. Cargar la molécula con RDKit
            is_smiles = file.filename.endswith(('.smi', '.smiles', '.txt'))
            if is_smiles:
                # Leer SMILES desde archivo
                with open(input_path, 'r') as f:
                    smiles_str = f.read().strip().split()[0]
                mol = Chem.MolFromSmiles(smiles_str)
                if mol is None:
                    raise HTTPException(status_code=400, detail="Invalid SMILES string")
            else:
                # Cargar desde archivo (SDF, MOL2, PDB)
                # Chem.SDMolSupplier es ideal para SDF, pero usaremos una carga genérica para otros formatos
                if file.filename.endswith('.sdf'):
                    supplier = Chem.SDMolSupplier(input_path, removeHs=False)
                    mol = next(supplier) # Toma la primera molécula
                elif file.filename.endswith(('.mol2', '.pdb')):
                    mol = Chem.MolFromMol2File(input_path, removeHs=False) if file.filename.endswith('.mol2') else Chem.MolFromPDBFile(input_path, removeHs=False)
                else:
                    raise HTTPException(status_code=400, detail="Unsupported file format. Use SDF, MOL2, PDB, or SMILES.")
                
                if mol is None:
                    raise HTTPException(status_code=400, detail="Could not read molecule from file")

            # 2. Añadir hidrógenos y generar coordenadas 3D si es necesario
            mol = Chem.AddHs(mol)
            # Si la molécula no tiene coordenadas 3D (ej. desde SMILES), generarlas
            if not any(atom.HasProp('_3D') for atom in mol.GetAtoms()):
                AllChem.EmbedMolecule(mol)
                AllChem.MMFFOptimizeMolecule(mol) # Optimización rápida

            # 3. Preparar la molécula con Meeko (API correcta)
            preparator = MoleculePreparation() # Ya no usa el argumento 'ph'
            mol_setups = preparator.prepare(mol) # Esto devuelve una lista

            if not mol_setups:
                raise HTTPException(status_code=400, detail="Meeko could not prepare the ligand")

            # 4. Generar el string PDBQT
            pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(mol_setups[0])
            if not is_ok:
                raise HTTPException(status_code=500, detail=f"Error generating PDBQT: {error_msg}")

            # Preparar nombre de salida
            base_name = os.path.splitext(file.filename)[0]
            output_filename = f"{base_name}_prepared.pdbqt"
            
            # Guardar PDBQT temporal
            output_path = os.path.join(tmpdir, output_filename)
            with open(output_path, "w") as f:
                f.write(pdbqt_string)
            
            # Devolver archivo
            return FileResponse(
                output_path,
                media_type="text/plain",
                filename=output_filename
            )
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)