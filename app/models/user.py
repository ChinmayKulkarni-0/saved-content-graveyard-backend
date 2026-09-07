from sqlalchemy import Boolean, Column, DateTime, Float, String, Text, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    tier = Column(String, default="free")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SavedItem(Base):
    __tablename__ = "saved_items"

    id = Column(String, primary_key=True)
    user_id = Column(String, index=True)
    description = Column(Text)
    category = Column(String)
    confidence = Column(Float)
    raw_text = Column(Text, nullable=True)
    product_links_json = Column(Text, default="[]")
    streaming_links_json = Column(Text, default="[]")
    tags_json = Column(Text, default="[]")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_deleted = Column(Boolean, default=False)
