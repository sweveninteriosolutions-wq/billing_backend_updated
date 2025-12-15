from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String(50), nullable=False, default="user")
    is_active = Column(Boolean, default=True, nullable=False)
    token_version = Column(Integer, nullable=False, default=0)
    last_login = Column(DateTime(timezone=True))
    is_online = Column(Boolean, default=False)
    version = Column(Integer, nullable=False, default=1)

    created_by_admin_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_admin = relationship("User", remote_side=[id], lazy="selectin")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")

    def __repr__(self):
        return f"<User id={self.id} username={self.username} role={self.role} created_by_admin_id={self.created_by_admin_id}>"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="refresh_tokens", lazy="selectin")

    def __repr__(self):
        return f"<RefreshToken id={self.id} user_id={self.user_id} revoked={self.revoked}>"
