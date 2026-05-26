"""
Tag data model for independent tag management.

Tags are managed as independent entities, not tied to specific agents.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict
import uuid


class Tag(BaseModel):
    """
    Tag entity model.
    
    Tags are independent entities that can be created, updated, and deleted.
    Other systems will associate tags with agents.
    """
    
    tag_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique tag identifier")
    name: str = Field(..., description="Tag name", max_length=50)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="Creation timestamp")
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="Update timestamp")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tag_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "生产环境",
                "created_at": "2026-05-07T10:00:00",
                "updated_at": "2026-05-07T10:00:00"
            }
        }
    )
    
    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc).isoformat()
