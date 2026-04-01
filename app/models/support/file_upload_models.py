# app/models/support/file_upload_models.py
from sqlalchemy import Column, Integer, String, BigInteger, Index
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, AuditMixin


class FileUpload(Base, TimestampMixin, AuditMixin):
    """
    Stores metadata for all uploaded files (GRN bills, supplier invoices, etc.)
    Actual files stored on disk under uploads/
    """
    __tablename__ = "file_uploads"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50), nullable=False, index=True)   # grn | supplier_bill | invoice
    entity_id = Column(Integer, nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=False)             # relative path on disk
    mime_type = Column(String(100), nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)

    __table_args__ = (Index("ix_file_upload_entity", "entity_type", "entity_id"),)

    def __repr__(self):
        return f"<FileUpload id={self.id} entity={self.entity_type}:{self.entity_id}>"
