"""HTTP API. Everything under ``/v1`` needs a bearer token; the token decides the app."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from notify_hub.auth import current_app
from notify_hub.schemas import (
    NotifyIn,
    NotifyResult,
    PublicKey,
    SubscriptionIn,
    SubscriptionOut,
    SubscriptionRef,
)
from notify_hub.service import EndpointTaken, NotifyService

router = APIRouter()
v1 = APIRouter(prefix="/v1", dependencies=[Depends(current_app)])


def service(request: Request) -> NotifyService:
    return request.app.state.service  # type: ignore[no-any-return]


@router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness and readiness. Touches neither the database nor the push services."""
    return {"status": "ok"}


@v1.get("/vapid-public-key")
async def vapid_public_key(request: Request) -> PublicKey:
    """The key the browser passes to ``pushManager.subscribe`` as ``applicationServerKey``."""
    return PublicKey(key=request.app.state.public_key)


@v1.put("/subscriptions")
async def subscribe(
    body: SubscriptionIn, app: str = Depends(current_app), svc: NotifyService = Depends(service)
) -> SubscriptionOut:
    try:
        row = await svc.subscribe(app, body)
    except EndpointTaken:
        raise HTTPException(status_code=409, detail="endpoint registered by another app") from None
    return SubscriptionOut.model_validate(row, from_attributes=True)


@v1.delete("/subscriptions", status_code=204)
async def unsubscribe(
    body: SubscriptionRef, app: str = Depends(current_app), svc: NotifyService = Depends(service)
) -> Response:
    """Idempotent: deleting an endpoint that is not there is still a 204."""
    await svc.unsubscribe(app, str(body.endpoint))
    return Response(status_code=204)


@v1.get("/subscriptions")
async def subscriptions(
    app: str = Depends(current_app), svc: NotifyService = Depends(service)
) -> list[SubscriptionOut]:
    return [SubscriptionOut.model_validate(row, from_attributes=True) for row in await svc.devices(app)]


@v1.post("/notify")
async def notify(
    body: NotifyIn, app: str = Depends(current_app), svc: NotifyService = Depends(service)
) -> NotifyResult:
    """Send to every device of the calling app. Zero devices is not an error: ``sent`` is 0."""
    return await svc.notify(app, body)


router.include_router(v1)

__all__ = ["router"]
