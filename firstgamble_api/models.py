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


class BuyRaffleTicketRequest(BaseModel):
    count: int = Field(1, ge=1, le=100)


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminPrizeRequest(BaseModel):
    name: str


class AdminPrizeUpdateRequest(BaseModel):
    name: Optional[str] = None


class AdminDrawRequest(BaseModel):
    force: Optional[bool] = False


class AdminFindUserRequest(BaseModel):
    nickname: str


class AdminSetPointsRequest(BaseModel):
    user_id: Optional[int] = None
    nickname: Optional[str] = None
    points_delta: Optional[int] = None
    new_balance: Optional[int] = None
