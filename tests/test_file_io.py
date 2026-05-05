import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from file_io import save_upload_file, validate_file_extension


class FakeUploadFile:
    def __init__(self, content: bytes):
        self.content = content
        self.offset = 0

    async def read(self, size: int) -> bytes:
        chunk = self.content[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


def output_path(name: str) -> Path:
    root = Path("tmp_test") / "file_io"
    root.mkdir(parents=True, exist_ok=True)
    return root / name


def test_save_upload_file_writes_uploaded_content():
    destination = output_path("saved_upload.smi")

    asyncio.run(save_upload_file(FakeUploadFile(b"CCO ethanol\n"), str(destination), 1024))

    assert destination.read_bytes() == b"CCO ethanol\n"


def test_save_upload_file_rejects_empty_upload():
    destination = output_path("empty_upload.smi")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(save_upload_file(FakeUploadFile(b""), str(destination), 1024))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Uploaded file is empty"


def test_save_upload_file_rejects_upload_over_size_limit():
    destination = output_path("oversized_upload.smi")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(save_upload_file(FakeUploadFile(b"abcdef"), str(destination), 5))

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail["message"] == "Uploaded file exceeds the 5 byte limit"
    assert exc_info.value.detail["limits"]["single_upload_max_bytes"] > 0


def test_validate_file_extension_accepts_case_insensitive_extensions():
    ext = validate_file_extension(
        "LIGAND.SMI",
        {".smi", ".smiles"},
        "unsupported",
    )

    assert ext == ".smi"


def test_validate_file_extension_accepts_compound_extensions():
    ext = validate_file_extension(
        "docked.PDBQT.GZ",
        {".pdbqt", ".pdbqt.gz"},
        "unsupported",
    )

    assert ext == ".pdbqt.gz"


def test_validate_file_extension_rejects_unexpected_extension():
    with pytest.raises(HTTPException) as exc_info:
        validate_file_extension("ligand.csv", {".smi"}, "unsupported")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "unsupported"
