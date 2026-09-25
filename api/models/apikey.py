from datetime import datetime

from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(default="default", max_length=200)


class ApiKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    rate_limit_per_minute: int
    revoked: bool
    created_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyCreatedOut(ApiKeyOut):
    # Only present on the create response — the raw key is never stored and
    # can't be retrieved again after this.
    key: str
