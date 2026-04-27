import re

from fastapi import HTTPException

from config import (
    MAX_BATCH_MOLECULES,
    MAX_BATCH_PDBQT_FILES,
    MAX_BATCH_TOTAL_PDBQT_BYTES,
    MAX_BATCH_UPLOAD_SIZE_BYTES,
    MAX_MINIMIZATION_MAX_ITERS,
    MAX_SCRUBBED_STATES_PER_LIGAND,
)


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w.-]+", "_", name).strip("._")
    return name or "ligand"


def sanitize_ligand_id(name: str, fallback_prefix: str, index: int) -> str:
    sanitized = sanitize_filename(name)
    if sanitized == "ligand" and not name.strip():
        sanitized = f"{fallback_prefix}_{index}"
    return sanitized


def get_batch_limit_summary() -> dict:
    return {
        "batch_upload_max_bytes": MAX_BATCH_UPLOAD_SIZE_BYTES,
        "batch_max_molecules": MAX_BATCH_MOLECULES,
        "batch_max_scrubbed_states_per_ligand": MAX_SCRUBBED_STATES_PER_LIGAND,
        "batch_max_generated_pdbqt_files": MAX_BATCH_PDBQT_FILES,
        "batch_max_total_pdbqt_bytes": MAX_BATCH_TOTAL_PDBQT_BYTES,
    }


def validate_minimization_max_iters(max_iters: int) -> int:
    if max_iters < 1 or max_iters > MAX_MINIMIZATION_MAX_ITERS:
        raise HTTPException(
            status_code=400,
            detail=(
                "'minimization_max_iters' must be between 1 and "
                f"{MAX_MINIMIZATION_MAX_ITERS}"
            ),
        )

    return max_iters
