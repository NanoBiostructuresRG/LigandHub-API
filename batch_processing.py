import io
import json
import zipfile

from fastapi import HTTPException
from fastapi.responses import Response

from config import MAX_BATCH_MOLECULES
from utils import get_batch_limit_summary, sanitize_filename


def parse_smiles_records(input_path: str):
    records = []

    try:
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
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Batch SMILES library files must be valid UTF-8 text",
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


def build_batch_summary(records, results):
    successful = [result for result in results if result["status"] == "success"]
    failed = [result for result in results if result["status"] == "failed"]

    return {
        "total": len(records),
        "successful": len(successful),
        "failed": len(failed),
        "details": results,
    }


def build_batch_archive_name(record, safe_ligand_id: str, state_index: int, setup_index: int, setup_count: int) -> str:
    archive_name = f"line{record['line_number']}_{safe_ligand_id}_state{state_index}"
    if setup_count > 1:
        archive_name = f"{archive_name}_pose{setup_index}"
    archive_name = f"{archive_name}.pdbqt"
    return archive_name


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
