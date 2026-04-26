from fastapi import HTTPException

from config import MAX_BATCH_MOLECULES
from utils import get_batch_limit_summary


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


def build_batch_summary(records, results):
    successful = [result for result in results if result["status"] == "success"]
    failed = [result for result in results if result["status"] == "failed"]

    return {
        "total": len(records),
        "successful": len(successful),
        "failed": len(failed),
        "details": results,
    }
