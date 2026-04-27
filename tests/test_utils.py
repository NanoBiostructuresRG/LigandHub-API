import pytest
from fastapi import HTTPException

from config import MAX_MINIMIZATION_MAX_ITERS
from utils import (
    get_batch_limit_summary,
    sanitize_filename,
    sanitize_ligand_id,
    validate_minimization_max_iters,
)


def test_sanitize_filename_keeps_safe_name_parts():
    assert sanitize_filename("ligand 1/sample?.smi") == "ligand_1_sample_.smi"


def test_sanitize_filename_falls_back_for_empty_or_unsafe_names():
    assert sanitize_filename("") == "ligand"
    assert sanitize_filename("../") == "ligand"


def test_sanitize_ligand_id_uses_fallback_for_blank_input():
    assert sanitize_ligand_id("   ", "ligand", 3) == "ligand_3"


def test_get_batch_limit_summary_exposes_expected_keys():
    summary = get_batch_limit_summary()

    assert summary["batch_upload_max_bytes"] > 0
    assert summary["batch_max_molecules"] > 0
    assert summary["batch_max_generated_pdbqt_files"] > 0


def test_validate_minimization_max_iters_accepts_valid_value():
    assert validate_minimization_max_iters(MAX_MINIMIZATION_MAX_ITERS) == MAX_MINIMIZATION_MAX_ITERS


def test_validate_minimization_max_iters_rejects_out_of_range_value():
    with pytest.raises(HTTPException) as exc_info:
        validate_minimization_max_iters(0)

    assert exc_info.value.status_code == 400
    assert "minimization_max_iters" in exc_info.value.detail
