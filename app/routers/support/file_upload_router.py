# app/routers/support/file_upload_router.py
import os
import uuid
import logging
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response, APIResponse
from app.models.support.file_upload_models import FileUpload

logger = logging.getLogger(__name__)

UPLOAD_ROOT = os.getenv("UPLOAD_ROOT", "uploads")
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_FILE_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

router = APIRouter(prefix="/files", tags=["File Uploads"])


async def _save_file(entity_type: str, entity_id: int, file: UploadFile) -> tuple[str, int]:
    """Save file to disk async and return (relative_path, file_size_bytes)."""
    import aiofiles
    folder = os.path.join(UPLOAD_ROOT, entity_type)
    os.makedirs(folder, exist_ok=True)

    ext = os.path.splitext(file.filename or "file")[1].lower() or ".bin"
    unique_name = f"{entity_id}_{uuid.uuid4().hex}{ext}"
    full_path = os.path.join(folder, unique_name)
    rel_path = os.path.join(entity_type, unique_name)

    # Read in chunks to avoid loading huge files into memory
    total = 0
    chunks = []
    while True:
        chunk = await file.read(65536)  # 64KB chunks
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB} MB.",
            )
        chunks.append(chunk)

    async with aiofiles.open(full_path, "wb") as f:
        for chunk in chunks:
            await f.write(chunk)

    return rel_path, total


@router.post("/upload")
async def upload_file(
    entity_type: str = Query(..., description="grn | supplier_bill | invoice"),
    entity_id: int = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory", "cashier"])),
):
    """Upload a file and associate it with an entity."""
    if entity_type not in ("grn", "supplier_bill", "invoice"):
        raise HTTPException(400, detail="Invalid entity_type. Use: grn, supplier_bill, invoice")

    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(415, detail="Only JPEG, PNG and PDF files are allowed.")

    try:
        rel_path, file_size = await _save_file(entity_type, entity_id, file)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File save error: {e}")
        raise HTTPException(500, detail="Failed to save file.")

    record = FileUpload(
        entity_type=entity_type,
        entity_id=entity_id,
        original_filename=file.filename or "upload",
        storage_path=rel_path,
        mime_type=content_type,
        file_size_bytes=file_size,
        created_by_id=user.id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return success_response("File uploaded successfully", {
        "id": record.id,
        "entity_type": record.entity_type,
        "entity_id": record.entity_id,
        "original_filename": record.original_filename,
        "storage_path": record.storage_path,
        "mime_type": record.mime_type,
        "file_size_bytes": record.file_size_bytes,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    })


@router.get("/by-entity")
async def list_files_for_entity(
    entity_type: str = Query(...),
    entity_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory", "cashier", "manager"])),
):
    result = await db.execute(
        select(FileUpload).where(
            FileUpload.entity_type == entity_type,
            FileUpload.entity_id == entity_id,
        )
    )
    records = result.scalars().all()
    return success_response("Files retrieved", [
        {
            "id": r.id,
            "original_filename": r.original_filename,
            "storage_path": r.storage_path,
            "mime_type": r.mime_type,
            "file_size_bytes": r.file_size_bytes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ])


@router.get("/download/{file_id}")
async def download_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory", "cashier", "manager"])),
):
    record = await db.get(FileUpload, file_id)
    if not record:
        raise HTTPException(404, detail="File not found")

    full_path = os.path.join(UPLOAD_ROOT, record.storage_path)
    if not os.path.exists(full_path):
        raise HTTPException(404, detail="File not found on disk")

    return FileResponse(
        full_path,
        media_type=record.mime_type or "application/octet-stream",
        filename=record.original_filename,
    )
