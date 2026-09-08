from pydantic import BaseModel


class UsageResponse(BaseModel):
    """Monthly freemium usage for the current user.

    ``remaining`` is an integer for free users and the string ``"unlimited"``
    for pro users; ``limit`` stays ``null`` for pro users.
    """

    free_usage_count: int
    usage_month: int | None
    usage_year: int | None
    is_pro: bool
    limit: int | None
    remaining: int | str