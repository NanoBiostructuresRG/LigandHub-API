from fastapi import HTTPException, UploadFile

from config import MAX_BATCH_UPLOAD_SIZE_BYTES, MAX_UPLOAD_SIZE_BYTES
from utils import get_batch_limit_summary


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
