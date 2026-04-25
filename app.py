"""
LigandHub API - Backend for ligand preparation using Meeko
Endpoint: /prepare_ligand
"""

import os
import re
import tempfile
import logging
import io
import json
import zipfile

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import uvicorn

from meeko import MoleculePreparation, PDBQTMolecule, PDBQTWriterLegacy, RDKitMolCreate
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem
from rdkit.Chem.rdchem import AtomValenceException

from config import (
    ALLOWED_ORIGINS,
    COMMON_ELEMENTS,
    DEFAULT_MINIMIZATION_MAX_ITERS,
    MAX_BATCH_MOLECULES,
    MAX_BATCH_PDBQT_FILES,
    MAX_BATCH_TOTAL_PDBQT_BYTES,
    MAX_BATCH_UPLOAD_SIZE_BYTES,
    MAX_SCRUBBED_STATES_PER_LIGAND,
    MAX_UPLOAD_SIZE_BYTES,
    METALS,
    SUPPORTED_CHARGE_MODELS,
)
from utils import (
    get_batch_limit_summary,
    sanitize_filename,
    sanitize_ligand_id,
    validate_minimization_max_iters,
)

try:
    from molscrub import Scrub
except ImportError:
    Scrub = None

app = FastAPI(
    title="LigandHub API",
    description="Ligand preparation for AutoDock Vina using Meeko"
)

logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://nanobiostructuresrg\.github\.io",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-LigandHub-Warnings"],
)


class BatchLimitExceeded(Exception):
    def __init__(self, detail: dict):
        self.detail = detail


@app.get("/")
async def root():
    return {"message": "LigandHub API is running", "status": "online"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/limits")
async def limits():
    return {
        "service_mode": "prototype",
        "notes": [
            "Batch limits are intentionally conservative for a small Render deployment.",
            "If you need larger libraries, move batch processing to an async worker or workflow."
        ],
        "limits": {
            "single_upload_max_bytes": MAX_UPLOAD_SIZE_BYTES,
            **get_batch_limit_summary(),
        },
    }


@app.post("/validate")
async def validate_smiles_endpoint(smiles: str = Form(...)):
    """
    Validate a SMILES string and return structural errors or warnings without running Meeko.
    """
    mol, errors, warnings = full_validation(smiles)

    return {
        "valid": mol is not None and not errors,
        "errors": errors,
        "warnings": warnings,
        "smiles": smiles,
    }


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
                    detail={
                        "message": f"Uploaded file exceeds the {max_size_bytes} byte limit",
                        "suggestion": "Upload a smaller file or split the library into smaller batches.",
                        "limits": get_batch_limit_summary() if max_size_bytes == MAX_BATCH_UPLOAD_SIZE_BYTES else {
                            "single_upload_max_bytes": MAX_UPLOAD_SIZE_BYTES,
                        },
                    }
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


def ensure_3d_and_hydrogens(
    mol,
    energy_minimization: bool | None = None,
    minimization_max_iters: int = DEFAULT_MINIMIZATION_MAX_ITERS,
):
    input_has_3d = (
        mol.GetNumConformers() > 0 and
        mol.GetConformer().Is3D()
    )

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

    should_minimize = energy_minimization if energy_minimization is not None else not input_has_3d

    if should_minimize:
        try:
            mmff_props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
            if mmff_props is not None:
                AllChem.MMFFOptimizeMolecule(mol, mmffVariant="MMFF94", maxIters=minimization_max_iters)
            elif AllChem.UFFHasAllMoleculeParams(mol):
                AllChem.UFFOptimizeMolecule(mol, maxIters=minimization_max_iters)
            else:
                logger.info("No MMFF94 or UFF parameters available; skipping ligand minimization")
        except Exception:
            logger.exception("Ligand minimization failed; continuing with current geometry")

    return mol


def parse_smiles_records(input_path: str):
    records = []

    with open(input_path, "r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 2:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Batch processing requires a .smi file with at least two columns per line: "
                        "SMILES and ligand ID"
                    ),
                )

            records.append(
                {
                    "line_number": line_number,
                    "smiles": parts[0],
                    "ligand_id": parts[1],
                }
            )

    if not records:
        raise HTTPException(status_code=400, detail="No valid molecules found in .smi file")

    if len(records) > MAX_BATCH_MOLECULES:
        raise HTTPException(
            status_code=413,
            detail={
                "message": f"Batch request exceeds the prototype limit of {MAX_BATCH_MOLECULES} molecules.",
                "suggestion": "Split the library into smaller files for this Render deployment.",
                "limits": get_batch_limit_summary(),
            },
        )

    return records


def scrub_molecule_states(
    mol,
    energy_minimization: bool | None = None,
    minimization_max_iters: int = DEFAULT_MINIMIZATION_MAX_ITERS,
):
    if Scrub is None:
        raise HTTPException(
            status_code=500,
            detail="molscrub is not installed in the runtime environment",
        )

    scrubber = Scrub(ph_low=7.4, ph_high=7.4)
    scrubbed_states = list(scrubber(mol))

    if not scrubbed_states:
        raise HTTPException(status_code=400, detail="Scrub could not generate any ligand state")

    if len(scrubbed_states) > MAX_SCRUBBED_STATES_PER_LIGAND:
        raise HTTPException(
            status_code=413,
            detail={
                "message": (
                    "Scrub generated too many states for this ligand for the current prototype limit. "
                    f"Maximum allowed states per ligand: {MAX_SCRUBBED_STATES_PER_LIGAND}"
                ),
                "suggestion": "Process this ligand separately or reduce the batch complexity.",
                "limits": get_batch_limit_summary(),
            },
        )

    prepared_states = []
    for state in scrubbed_states:
        state_with_geometry = ensure_3d_and_hydrogens(
            state,
            energy_minimization=energy_minimization,
            minimization_max_iters=minimization_max_iters,
        )
        prepared_states.append(state_with_geometry)

    return prepared_states


def create_zip_response(zip_basename: str, files_to_write: dict[str, str], summary_payload: dict) -> Response:
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for archive_name, content in files_to_write.items():
            zip_file.writestr(archive_name, content)

        zip_file.writestr("summary.json", json.dumps(summary_payload, indent=2))

    zip_bytes = zip_buffer.getvalue()
    output_filename = f"{sanitize_filename(zip_basename)}_pdbqt_batch.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{output_filename}"'
        },
    )


@app.post("/prepare_ligand")
async def prepare_ligand(
    file: UploadFile = File(...),
    filename: str = Form("ligand"),
    output_format: str = Form("pdbqt"),
    merge_h: bool = Form(True),
    charge_model: str = Form("gasteiger"),
    energy_minimization: bool | None = Form(None),
    minimization_max_iters: int = Form(DEFAULT_MINIMIZATION_MAX_ITERS),
):
    """
    Prepare ligand for AutoDock Vina using Meeko.

    Notes:
    - `merge_h=True` merges hydrogens using the default behavior.
    - `merge_h=False` keeps hydrogens separate.
    - `charge_model` supports: gasteiger, nagl, espaloma, zero.
    - `energy_minimization` defaults to true for SMILES/2D inputs and false for 3D files.
    - `minimization_max_iters` controls MMFF94/UFF minimization iterations, maximum 2000.
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

    minimization_max_iters = validate_minimization_max_iters(minimization_max_iters)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, sanitize_filename(file.filename))
            await save_upload_file(file, input_path, MAX_UPLOAD_SIZE_BYTES)

            mol, validation_warnings = load_molecule_from_file(input_path, file.filename)
            mol = ensure_3d_and_hydrogens(
                mol,
                energy_minimization=energy_minimization,
                minimization_max_iters=minimization_max_iters,
            )

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
                    "Content-Disposition": f'attachment; filename="{output_filename}"',
                    "X-LigandHub-Warnings": json.dumps(
                        [warning["message"] for warning in validation_warnings]
                    ),
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected server error while preparing ligand")
        raise HTTPException(status_code=500, detail="Unexpected server error")


@app.post("/prepare_ligand_batch")
async def prepare_ligand_batch(
    file: UploadFile = File(...),
    filename: str = Form("ligands"),
    merge_h: bool = Form(True),
    charge_model: str = Form("gasteiger"),
    energy_minimization: bool | None = Form(None),
    minimization_max_iters: int = Form(DEFAULT_MINIMIZATION_MAX_ITERS),
):
    """
    Prepare multiple ligands from a SMILES library file and return a ZIP with all PDBQT files.

    Notes:
    - Input must be a `.smi`, `.smiles`, or `.txt` file with at least two columns: SMILES and ligand ID.
    - Scrub (`molscrub`) is used to enumerate ligand states before Meeko preparation.
    - Each generated state is exported as an individual `.pdbqt` file inside the ZIP.
    - The ZIP also includes `summary.json` with success and failure details.
    - Prototype Render limits for this endpoint: batch upload <= 1 MB, max 100 molecules,
      max 8 scrubbed states per ligand, max 250 generated PDBQT files, and max 25 MB
      of generated PDBQT content before ZIP packaging.
    - `energy_minimization` defaults to true for generated 3D geometries.
    - `minimization_max_iters` controls MMFF94/UFF minimization iterations, maximum 2000.
    """

    if not file.filename:
        raise HTTPException(status_code=400, detail="No input filename provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".smi", ".smiles", ".txt"}:
        raise HTTPException(
            status_code=400,
            detail="Batch processing requires a .smi, .smiles, or .txt SMILES library file",
        )

    charge_model = charge_model.strip().lower()
    if charge_model not in SUPPORTED_CHARGE_MODELS:
        raise HTTPException(
            status_code=400,
            detail="Invalid 'charge_model'. Use one of: gasteiger, nagl, espaloma, zero"
        )

    minimization_max_iters = validate_minimization_max_iters(minimization_max_iters)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, sanitize_filename(file.filename))
            await save_upload_file(file, input_path, MAX_BATCH_UPLOAD_SIZE_BYTES)

            records = parse_smiles_records(input_path)
            merge_these = ("H",) if merge_h else ()
            files_to_zip = {}
            results = []
            total_pdbqt_files = 0
            total_pdbqt_bytes = 0

            for index, record in enumerate(records, start=1):
                ligand_id = record["ligand_id"]
                smiles = record["smiles"]
                safe_ligand_id = sanitize_ligand_id(ligand_id, "ligand", index)

                try:
                    mol, validation_errors, validation_warnings = full_validation(smiles)
                    if validation_errors:
                        results.append({
                            "line": record["line_number"],
                            "id": ligand_id,
                            "status": "failed",
                            "error": "Validation failed",
                            "errors": validation_errors,
                            "warnings": validation_warnings,
                        })
                        continue

                    scrubbed_states = scrub_molecule_states(
                        mol,
                        energy_minimization=energy_minimization,
                        minimization_max_iters=minimization_max_iters,
                    )
                    generated_files = []

                    for state_index, scrubbed_mol in enumerate(scrubbed_states, start=1):
                        preparator = MoleculePreparation(
                            merge_these_atom_types=merge_these,
                            charge_model=charge_model,
                        )
                        mol_setups = preparator.prepare(scrubbed_mol)

                        if not mol_setups:
                            raise HTTPException(
                                status_code=400,
                                detail="Meeko could not prepare the scrubbed ligand state",
                            )

                        for setup_index, mol_setup in enumerate(mol_setups, start=1):
                            pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(mol_setup)

                            if not is_ok:
                                raise HTTPException(
                                    status_code=500,
                                    detail=f"Error generating PDBQT: {error_msg}",
                                )

                            archive_name = f"line{record['line_number']}_{safe_ligand_id}_state{state_index}"
                            if len(mol_setups) > 1:
                                archive_name = f"{archive_name}_pose{setup_index}"
                            archive_name = f"{archive_name}.pdbqt"

                            total_pdbqt_files += 1
                            total_pdbqt_bytes += len(pdbqt_string.encode("utf-8"))

                            if total_pdbqt_files > MAX_BATCH_PDBQT_FILES:
                                raise BatchLimitExceeded(
                                    detail={
                                        "message": (
                                            "Batch request generated too many output files for the current "
                                            f"prototype limit. Maximum allowed: {MAX_BATCH_PDBQT_FILES}"
                                        ),
                                        "suggestion": (
                                            "Split the input library into smaller batches so each request "
                                            "produces fewer PDBQT files."
                                        ),
                                        "limits": get_batch_limit_summary(),
                                    },
                                )

                            if total_pdbqt_bytes > MAX_BATCH_TOTAL_PDBQT_BYTES:
                                raise BatchLimitExceeded(
                                    detail={
                                        "message": (
                                            "Batch request generated too much output data for the current "
                                            "prototype limit."
                                        ),
                                        "suggestion": (
                                            "Split the library into smaller batches to reduce total output size."
                                        ),
                                        "limits": get_batch_limit_summary(),
                                    },
                                )

                            files_to_zip[archive_name] = pdbqt_string
                            generated_files.append(archive_name)

                    results.append({
                        "line": record["line_number"],
                        "id": ligand_id,
                        "status": "success",
                        "generated_files": generated_files,
                        "warnings": validation_warnings,
                    })

                except HTTPException as exc:
                    results.append({
                        "line": record["line_number"],
                        "id": ligand_id,
                        "status": "failed",
                        "error": exc.detail,
                    })
                except BatchLimitExceeded as exc:
                    raise HTTPException(status_code=413, detail=exc.detail)
                except Exception as exc:
                    logger.exception("Unexpected server error while preparing ligand batch item")
                    results.append({
                        "line": record["line_number"],
                        "id": ligand_id,
                        "status": "failed",
                        "error": "Unexpected server error while preparing this ligand",
                    })

            successful = [result for result in results if result["status"] == "success"]
            failed = [result for result in results if result["status"] == "failed"]

            if not files_to_zip:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "No PDBQT files could be generated from the uploaded library",
                        "summary": {
                            "total": len(records),
                            "successful": 0,
                            "failed": len(failed),
                            "details": results,
                        },
                    },
                )

            summary_payload = {
                "total": len(records),
                "successful": len(successful),
                "failed": len(failed),
                "details": results,
            }

            return create_zip_response(filename or file.filename, files_to_zip, summary_payload)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected server error while preparing ligand batch")
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
