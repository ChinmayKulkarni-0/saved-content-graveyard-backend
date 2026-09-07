from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.schemas.library import SavedItem

router = APIRouter()


@router.get("/", response_model=list[SavedItem])
async def get_saved_items(current_user: str = Depends(get_current_user)):
    # TODO: Fetch from database
    return []


@router.get("/{item_id}", response_model=SavedItem)
async def get_saved_item(item_id: str, current_user: str = Depends(get_current_user)):
    # TODO: Fetch from database
    return None


@router.delete("/{item_id}")
async def delete_saved_item(
    item_id: str, current_user: str = Depends(get_current_user)
):
    # TODO: Delete from database
    return {"status": "deleted"}
