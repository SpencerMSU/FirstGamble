from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AuthContext(BaseModel):
    user_id: int
    from_telegram: bool
    from_conserve: bool
    username: Optional[str] = None
    tg_id: Optional[int] = None


class AddPointRequest(BaseModel):
    user_id: Optional[str] = None
    game: str
    delta: Optional[int] = 1


class ReportGameRequest(BaseModel):
    user_id: Optional[str] = None
    game: str
    result: str


class UpdateProfileRequest(BaseModel):
    user_id: Optional[str] = None
    name: Optional[str] = None
    username: Optional[str] = None


class RpgGatherRequest(BaseModel):
    user_id: Optional[str] = None


class RpgBuyRequest(BaseModel):
    user_id: Optional[str] = None
    category: str
    item_id: str


class RpgConvertRequest(BaseModel):
    user_id: Optional[str] = None
    from_: str = Field(alias="from")
    to: str
    amount: int

    model_config = {"populate_by_name": True}


class RaffleBuyRequest(BaseModel):
    user_id: Optional[str] = None
