from sqlalchemy import Column, Integer, String, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin


class UserActivity(Base, TimestampMixin):
    """Immutable audit log. APPEND-ONLY. Never updated, never deleted."""

    __tablename__ = "user_activity"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    username_snapshot = Column(String(150), nullable=False, index=True)
    message = Column(String, nullable=False)

    user = relationship("User", lazy="selectin")

    __table_args__ = (Index("ix_user_activity_user_created", "user_id", "created_at"),)

    def __repr__(self):
        return f"<UserActivity id={self.id} user={self.username_snapshot}>"
