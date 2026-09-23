from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base

class EssayRubric(Base):
    __tablename__ = "essay_rubrics"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(36), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    content = Column(Text, nullable=True)
    summary_prompt = Column(Text, nullable=True)
    comment_prompt = Column(Text, nullable=True)
    rewrite_prompt = Column(Text, nullable=True)
    guidance_prompt = Column(Text, nullable=True)
    scoring_prompt = Column(Text, nullable=True)
    topic_text = Column(Text, nullable=True)
    topic_image_base64 = Column(Text, nullable=True)
    dimensions_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
