"""站内提醒 APIs（#32）。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from schemas import APIResponse
from services import notification_service


router = APIRouter()


class ReminderSettingsRequest(BaseModel):
    reminder_enabled: bool = True


def _fail(exc: Exception):
    raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=APIResponse)
async def list_notifications(current_user: dict = Depends(get_current_user)):
    try:
        return APIResponse(data=notification_service.list_notifications(current_user["id"]))
    except Exception as exc:
        _fail(exc)


@router.post("/read-all", response_model=APIResponse)
async def mark_all_read(current_user: dict = Depends(get_current_user)):
    try:
        return APIResponse(data={"unread_count": notification_service.mark_all_read(current_user["id"])})
    except Exception as exc:
        _fail(exc)


@router.post("/{notification_id}/read", response_model=APIResponse)
async def mark_read(notification_id: int, current_user: dict = Depends(get_current_user)):
    try:
        return APIResponse(data={"unread_count": notification_service.mark_read(current_user["id"], notification_id)})
    except Exception as exc:
        _fail(exc)


@router.get("/settings", response_model=APIResponse)
async def get_settings(current_user: dict = Depends(get_current_user)):
    try:
        data = notification_service.list_notifications(current_user["id"], limit=1)
        return APIResponse(data={"reminder_enabled": data.get("reminder_enabled", True)})
    except Exception as exc:
        _fail(exc)


@router.put("/settings", response_model=APIResponse)
async def update_settings(req: ReminderSettingsRequest, current_user: dict = Depends(get_current_user)):
    try:
        enabled = notification_service.set_reminder_enabled(current_user["id"], req.reminder_enabled)
        return APIResponse(data={"reminder_enabled": enabled})
    except Exception as exc:
        _fail(exc)
