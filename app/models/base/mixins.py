from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declared_attr, relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property

class TimestampMixin:
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now()
    )


class SoftDeleteMixin:
    is_deleted = Column(Boolean, default=False, nullable=False)


class AuditMixin:
    @declared_attr
    def created_by_id(cls):
        return Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    @declared_attr
    def updated_by_id(cls):
        return Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    @declared_attr
    def created_by(cls):
        return relationship(
            "User",
            foreign_keys=[cls.created_by_id],
            lazy="joined"
        )

    @declared_attr
    def updated_by(cls):
        return relationship(
            "User",
            foreign_keys=[cls.updated_by_id],
            lazy="joined"
        )

    # ----------------------------
    # Convenience accessors
    # ----------------------------
    @hybrid_property
    def created_by_username(self):
        return self.created_by.username if self.created_by else None

    @hybrid_property
    def updated_by_username(self):
        return self.updated_by.username if self.updated_by else None
