from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declared_attr, relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class SoftDeleteMixin:
    is_deleted = Column(Boolean, default=False, nullable=False)

class AuditMixin:
    # PERF-P1-4 FIXED: Changed lazy="selectin" to lazy="raise" on audit relationships.
    #
    # PROBLEM: lazy="selectin" fired 2 extra SELECT queries per model instance on EVERY
    # fetch — one for created_by, one for updated_by. On a list of 20 invoices this meant
    # 40 additional DB round trips, even when audit user info wasn't needed.
    #
    # FIX: lazy="raise" causes SQLAlchemy to raise an error if the relationship is accessed
    # without being explicitly loaded. This forces service-layer code to be intentional:
    #   - Use selectinload(Model.created_by) / selectinload(Model.updated_by) when needed.
    #   - Use noload(Model.created_by) / noload(Model.updated_by) when not needed.
    #
    # MIGRATION NOTE: Any service that accesses .created_by or .updated_by directly
    # (e.g. in response serialization) will raise a greenlet_spawn error until you add
    # explicit selectinload() to that query. Search for created_by_username / updated_by_username
    # in schemas and add the load options accordingly.

    @declared_attr
    def created_by_id(cls):
        return Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    @declared_attr
    def updated_by_id(cls):
        return Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    @declared_attr
    def created_by(cls):
        return relationship("User", foreign_keys=[cls.created_by_id], lazy="raise")

    @declared_attr
    def updated_by(cls):
        return relationship("User", foreign_keys=[cls.updated_by_id], lazy="raise")

    @hybrid_property
    def created_by_username(self):
        # FIXED (BUG-4): Use __dict__ lookup instead of self.created_by to avoid
        # triggering lazy="raise" when the relationship has not been selectinloaded.
        # Callers that need this value must load it via selectinload(Model.created_by).
        cb = self.__dict__.get("created_by")
        return cb.username if cb else None

    @hybrid_property
    def updated_by_username(self):
        ub = self.__dict__.get("updated_by")
        return ub.username if ub else None
