"""
LigandHub API - Backend for ligand preparation using Meeko
Endpoint: /prepare_ligand
"""

import os
import tempfile
import logging
import io
import json
import zipfile

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import uvicorn

from config import (
    ALLOWED_ORIGINS,
    DEFAULT_MINIMIZATION_MAX_ITERS,
    MAX_BATCH_MOLECULES,
    MAX_BATCH_PDBQT_FILES,
    MAX_BATCH_TOTAL_PDBQT_BYTES,
    MAX_BATCH_UPLOAD_SIZE_BYTES,
    MAX_UPLOAD_SIZE_BYTES,
    SUPPORTED_CHARGE_MODELS,
)
from utils import (
    get_batch_limit_summary,
    sanitize_filename,
    sanitize_ligand_id,
    validate_minimization_max_iters,
)
from docking_io import detect_docking_results_format, export_docking_results_to_sdf_string
from file_io import save_upload_file
from molecule_io import load_molecule_from_file
from pdbqt_writer import prepare_molecule_setups, write_pdbqt_string
from preparation import ensure_3d_and_hydrogens, scrub_molecule_states
from validation import full_validation

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

            mol_setups = prepare_molecule_setups(
                mol,
                merge_h=merge_h,
                charge_model=charge_model,
                empty_error_detail="Meeko could not prepare the ligand",
            )

            pdbqt_string = write_pdbqt_string(mol_setups[0])

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
                        mol_setups = prepare_molecule_setups(
                            scrubbed_mol,
                            merge_h=merge_h,
                            charge_model=charge_model,
                            empty_error_detail="Meeko could not prepare the scrubbed ligand state",
                        )

                        for setup_index, mol_setup in enumerate(mol_setups, start=1):
                            pdbqt_string = write_pdbqt_string(mol_setup)

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
