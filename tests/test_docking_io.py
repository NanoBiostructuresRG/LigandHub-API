import pytest
from fastapi import HTTPException

from docking_io import detect_docking_results_format


@pytest.mark.parametrize(
    ("filename", "expected_format"),
    [
        ("results.pdbqt", "pdbqt"),
        ("results.pdbqt.gz", "pdbqt"),
        ("results.dlg", "dlg"),
        ("results.dlg.gz", "dlg"),
        ("RESULTS.PDBQT", "pdbqt"),
        ("RESULTS.DLG.GZ", "dlg"),
    ],
)
def test_detect_docking_results_format_accepts_supported_extensions(filename, expected_format):
    assert detect_docking_results_format(filename) == expected_format


def test_detect_docking_results_format_rejects_unsupported_extension():
    with pytest.raises(HTTPException) as exc_info:
        detect_docking_results_format("results.sdf")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Unsupported docking results format. Use PDBQT or DLG files."
