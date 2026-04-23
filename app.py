"""
LigandHub API - Backend for ligand preparation using Meeko
Endpoint: /prepare_ligand
"""

import os
import tempfile
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Meeko imports
from meeko import MoleculePreparation, PDBQTWriterLegacy, RDKitMolCreate

app = FastAPI(title="LigandHub API", description="Ligand preparation for AutoDock Vina using Meeko")

# Enable CORS for frontend (GitHub Pages)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, limitar a tu dominio de GitHub Pages
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
    output_format: str = Form("pdbqt")
):
    """
    Prepare ligand for AutoDock Vina using Meeko
    
    - Input: SDF, MOL2, PDB, or SMILES file
    - Output: PDBQT file ready for docking
    """
    
    # Validar formato de salida
    if output_format not in ["pdbqt", "pdb", "both"]:
        raise HTTPException(status_code=400, detail="Invalid output format")
    
    # Crear directorio temporal
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Guardar archivo subido
            input_path = os.path.join(tmpdir, file.filename)
            content = await file.read()
            
            with open(input_path, "wb") as f:
                f.write(content)
            
            # Detectar si es SMILES (archivo .smi)
            is_smiles = file.filename.endswith(('.smi', '.smiles', '.txt'))
            
            if is_smiles:
                # Leer SMILES desde archivo
                with open(input_path, 'r') as f:
                    smiles_str = f.read().strip().split()[0]
                
                # Crear molécula RDKit desde SMILES
                mol = RDKitMolCreate.from_smiles(smiles_str)
                if mol is None:
                    raise HTTPException(status_code=400, detail="Invalid SMILES string")
                
                # Crear objeto de preparación
                preparator = MoleculePreparation(ph=ph)
                
                # Preparar molécula
                mol_prepared = preparator.prepare(mol)
                
            else:
                # Cargar molécula desde archivo (SDF, MOL2, PDB)
                preparator = MoleculePreparation(ph=ph)
                mol_prepared = preparator.prepare_from_file(input_path)
            
            if mol_prepared is None:
                raise HTTPException(status_code=400, detail="Failed to prepare ligand")
            
            # Generar PDBQT
            pdbqt_string = PDBQTWriterLegacy.write_string(mol_prepared)
            
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