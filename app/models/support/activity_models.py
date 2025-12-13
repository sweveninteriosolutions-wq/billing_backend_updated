# app/models/activity_models.py

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.base.mixins import TimestampMixin


class UserActivity(Base, TimestampMixin):
    """
    Immutable audit log.
    This table is APPEND-ONLY.
    """

    __tablename__ = "user_activity"

    id = Column(Integer, primary_key=True)
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    username_snapshot = Column(String(150), nullable=False, index=True)


    message = Column(String, nullable=False)

    user = relationship("User", lazy="joined")

    def __repr__(self):
        return f"<UserActivity id={self.id} user={self.username_snapshot}>"
