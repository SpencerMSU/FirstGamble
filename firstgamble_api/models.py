from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AuthContext(BaseModel):
    """Represents the authentication context of a user.

    Attributes:
        user_id: The user's unique identifier.
        from_telegram: Whether the user is authenticated via Telegram.
        from_conserve: Whether the user is authenticated via ConServe.
        username: The user's Telegram username.
        tg_id: The user's Telegram ID.
    """
    user_id: int
    from_telegram: bool
    from_conserve: bool
    username: Optional[str] = None
    tg_id: Optional[int] = None


class AddPointRequest(BaseModel):
    """Request model for adding points to a user's balance.

    Attributes:
        user_id: The user's unique identifier.
        game: The game for which the points are being added.
        delta: The number of points to add.
    """
    user_id: Optional[str] = None
    game: str
    delta: Optional[int] = 1


class DiceExternalAwardRequest(BaseModel):
    """Request model for awarding points from an external dice game.

    Attributes:
        Nick_Name: The user's nickname in the game.
        dice_sum: The sum of the dice roll.
    """
    Nick_Name: Optional[str] = None
    dice_sum: int


class ReportGameRequest(BaseModel):
    """Request model for reporting the result of a game.

    Attributes:
        user_id: The user's unique identifier.
        game: The game that was played.
        result: The result of the game (e.g., "win", "loss").
    """
    user_id: Optional[str] = None
    game: str
    result: str


class UpdateProfileRequest(BaseModel):
    """Request model for updating a user's profile.

    Attributes:
        user_id: The user's unique identifier.
        name: The user's new name.
        username: The user's new Telegram username.
        Nick_Name: The user's new in-game nickname.
    """
    user_id: Optional[str] = None
    name: Optional[str] = None
    username: Optional[str] = None
    Nick_Name: Optional[str] = None


class RpgGatherRequest(BaseModel):
    """Request model for gathering resources in the RPG minigame.

    Attributes:
        user_id: The user's unique identifier.
    """
    user_id: Optional[str] = None


class RpgBuyRequest(BaseModel):
    """Request model for buying an item in the RPG minigame.

    Attributes:
        user_id: The user's unique identifier.
        category: The category of the item to buy.
        item_id: The ID of the item to buy.
    """
    user_id: Optional[str] = None
    category: str
    item_id: str


class RpgConvertRequest(BaseModel):
    """Request model for converting resources in the RPG minigame.

    Attributes:
        user_id: The user's unique identifier.
        from_: The resource to convert from.
        to: The resource to convert to.
        amount: The amount of the target resource to receive.
    """
    user_id: Optional[str] = None
    from_: str = Field(alias="from")
    to: str
    amount: int

    model_config = {"populate_by_name": True}


class RpgAutoRequest(BaseModel):
    """Request model for managing auto-miners in the RPG minigame.

    Attributes:
        user_id: The user's unique identifier.
        action: The action to perform (e.g., "upgrade", "start").
        miner_id: The ID of the miner to manage.
    """
    user_id: Optional[str] = None
    action: str
    miner_id: str


class BuyRaffleTicketRequest(BaseModel):
    """Request model for buying raffle tickets.

    Attributes:
        count: The number of tickets to buy.
    """
    count: int = Field(1, ge=1, le=100)


class AdminLoginRequest(BaseModel):
    """Request model for admin login.

    Attributes:
        username: The admin's username.
        password: The admin's password.
    """
    username: str
    password: str


class AdminPrizeRequest(BaseModel):
    """Request model for creating a raffle prize.

    Attributes:
        name: The name of the prize.
    """
    name: str


class AdminPrizeUpdateRequest(BaseModel):
    """Request model for updating a raffle prize.

    Attributes:
        name: The new name of the prize.
    """
    name: Optional[str] = None


class AdminPublishPrizesRequest(BaseModel):
    """Request model for publishing raffle prizes.

    Attributes:
        visible: Whether the prizes should be visible to users.
    """
    visible: bool = True


class AdminEconomyUpdateRequest(BaseModel):
    """Request model for updating the RPG economy.

    Attributes:
        convert_rate: The new resource conversion rate.
        base_cd: The new base cooldown for gathering resources.
    """
    convert_rate: Optional[int] = Field(default=None, ge=1, le=1000)
    base_cd: Optional[int] = Field(default=None, ge=30, le=86400)


class AdminDrawRequest(BaseModel):
    """Request model for drawing raffle winners.

    Attributes:
        force: Whether to force a redraw if winners have already been drawn.
    """
    force: Optional[bool] = False


class AdminFindUserRequest(BaseModel):
    """Request model for finding a user by nickname.

    Attributes:
        nickname: The nickname of the user to find.
    """
    nickname: str


class AdminSetPointsRequest(BaseModel):
    """Request model for setting a user's points.

    Attributes:
        user_id: The user's unique identifier.
        nickname: The user's nickname.
        points_delta: The change in points.
        new_balance: The user's new total balance.
    """
    user_id: Optional[int] = None
    nickname: Optional[str] = None
    points_delta: Optional[int] = None
    new_balance: Optional[int] = None


class AdminGrantResourcesRequest(BaseModel):
    """Request model for granting RPG resources to a user.

    Attributes:
        user_id: The user's unique identifier.
        nickname: The user's nickname.
        resource: The resource to grant.
        amount: The amount of the resource to grant.
    """
    user_id: Optional[int] = None
    nickname: Optional[str] = None
    resource: str
    amount: int


class AchievementClaimRequest(BaseModel):
    """Request model for claiming an achievement reward.

    Attributes:
        achievement_id: The ID of the achievement to claim.
    """
    achievement_id: str


class ChatSendRequest(BaseModel):
    """Request model for sending a chat message.

    Attributes:
        text: The content of the message.
        sender_name: Optional sender name (used if not authenticated or overridden).
    """
    text: str
    sender_name: Optional[str] = None
