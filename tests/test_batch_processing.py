import io
import json
from pathlib import Path
import zipfile

import pytest
from fastapi import HTTPException

from batch_processing import (
    build_batch_archive_name,
    build_batch_summary,
    create_zip_response,
    parse_smiles_records,
)
from config import MAX_BATCH_MOLECULES


TEST_INPUT_DIR = Path("tmp_test/unit_inputs")


def write_test_smi_file(filename: str, content: str) -> Path:
    TEST_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEST_INPUT_DIR / filename
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_smiles_records_reads_valid_records_and_skips_comments():
    smi_file = write_test_smi_file("library.smi", "\n# comment\nCCO ethanol\nCCC propane extra_column\n")

    records = parse_smiles_records(str(smi_file))

    assert records == [
        {"line_number": 3, "smiles": "CCO", "ligand_id": "ethanol"},
        {"line_number": 4, "smiles": "CCC", "ligand_id": "propane"},
    ]


def test_parse_smiles_records_rejects_empty_file():
    smi_file = write_test_smi_file("empty.smi", "\n# only comments\n")

    with pytest.raises(HTTPException) as exc_info:
        parse_smiles_records(str(smi_file))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "No valid molecules found in .smi file"


def test_parse_smiles_records_rejects_missing_ligand_id():
    smi_file = write_test_smi_file("missing_id.smi", "CCO\n")

    with pytest.raises(HTTPException) as exc_info:
        parse_smiles_records(str(smi_file))

    assert exc_info.value.status_code == 400
    assert "at least two columns" in exc_info.value.detail


def test_parse_smiles_records_rejects_too_many_records():
    lines = [f"CCO ligand_{index}" for index in range(MAX_BATCH_MOLECULES + 1)]
    smi_file = write_test_smi_file("large.smi", "\n".join(lines))

    with pytest.raises(HTTPException) as exc_info:
        parse_smiles_records(str(smi_file))

    assert exc_info.value.status_code == 413
    assert "limits" in exc_info.value.detail


def test_build_batch_summary_counts_successful_and_failed_results():
    records = [{"ligand_id": "a"}, {"ligand_id": "b"}]
    results = [
        {"ligand_id": "a", "status": "success"},
        {"ligand_id": "b", "status": "failed"},
    ]

    summary = build_batch_summary(records, results)

    assert summary == {
        "total": 2,
        "successful": 1,
        "failed": 1,
        "details": results,
    }


def test_build_batch_archive_name_includes_pose_only_when_needed():
    record = {"line_number": 7}

    assert build_batch_archive_name(record, "ligand_a", 2, 1, 1) == "line7_ligand_a_state2.pdbqt"
    assert build_batch_archive_name(record, "ligand_a", 2, 3, 4) == "line7_ligand_a_state2_pose3.pdbqt"


def test_create_zip_response_contains_files_summary_and_sanitized_filename():
    response = create_zip_response(
        "../batch one",
        {"ligand_a.pdbqt": "PDBQT DATA"},
        {"total": 1, "successful": 1, "failed": 0, "details": []},
    )

    assert response.media_type == "application/zip"
    assert response.headers["Content-Disposition"] == 'attachment; filename="batch_one_pdbqt_batch.zip"'

    with zipfile.ZipFile(io.BytesIO(response.body)) as zip_file:
        assert zip_file.read("ligand_a.pdbqt").decode("utf-8") == "PDBQT DATA"
        summary = json.loads(zip_file.read("summary.json").decode("utf-8"))

    assert summary["total"] == 1
    assert summary["failed"] == 0
