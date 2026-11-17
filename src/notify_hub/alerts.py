"""Alertmanager webhooks → one push notification per alert group.

Alertmanager posts a group of alerts that share their grouping labels. The
phone gets one notification for the group: the first alert's summary as the
title, its description as the body, and a tag derived from ``groupKey`` so the
"resolved" message replaces the "firing" one instead of piling up.

Example:
    >>> group = AlertGroup(
    ...     status="firing",
    ...     groupKey='{}:{alertname="PgSharedDown"}',
    ...     alerts=[Alert(status="firing", labels={"alertname": "PgSharedDown", "severity": "critical"},
    ...                   annotations={"summary": "Postgres pg-shared è giù"})],
    ... )
    >>> note = to_notification(group)
    >>> note.title, note.urgency, note.tag == tag_for(group.groupKey)
    ('🔴 Postgres pg-shared è giù', 'high', True)
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict

from notify_hub.schemas import NotifyIn

Status = Literal["firing", "resolved"]

_TITLE_MAX = 120
_BODY_MAX = 1000


class Alert(BaseModel):
    """One alert of the group. Only the fields the notification uses."""

    model_config = ConfigDict(extra="ignore")

    status: Status
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}


class AlertGroup(BaseModel):
    """Alertmanager webhook payload (version 4). Unknown fields are ignored."""

    model_config = ConfigDict(extra="ignore")

    status: Status
    groupKey: str  # noqa: N815 - Alertmanager's own field name
    alerts: list[Alert]


def tag_for(group_key: str) -> str:
    """Stable tag for a group: the same group always replaces its last notification.

    Example:
        >>> tag_for("a") == tag_for("a"), tag_for("a") == tag_for("b"), len(tag_for("a"))
        (True, False, 22)
    """
    return "alert-" + hashlib.sha256(group_key.encode()).hexdigest()[:16]


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def to_notification(group: AlertGroup) -> NotifyIn:
    """The push notification for a webhook call.

    Firing alerts come first; with several, the body says how many more there are.
    A critical firing alert is pushed with high urgency, everything else normal.

    Example:
        >>> resolved = AlertGroup(status="resolved", groupKey="k", alerts=[
        ...     Alert(status="resolved", labels={"alertname": "PgBackupStale"})])
        >>> to_notification(resolved).title
        '✅ Risolto: PgBackupStale'
        >>> two = AlertGroup(status="firing", groupKey="k", alerts=[
        ...     Alert(status="firing", labels={"alertname": "X", "severity": "warning"},
        ...           annotations={"summary": "Disco al 85%", "description": "Libera spazio."}),
        ...     Alert(status="firing", labels={"alertname": "X"})])
        >>> n = to_notification(two)
        >>> n.title, n.body, n.urgency
        ('🟠 Disco al 85%', 'Libera spazio.\\n(+1 altra allerta)', 'normal')
    """
    alerts = sorted(group.alerts, key=lambda a: a.status != "firing") or [Alert(status=group.status)]
    first = alerts[0]
    name = first.labels.get("alertname", "Allerta")
    summary = first.annotations.get("summary", name)
    critical = first.labels.get("severity") == "critical"

    if group.status == "resolved":
        title = f"✅ Risolto: {summary}"
    else:
        title = f"{'🔴' if critical else '🟠'} {summary}"

    body = first.annotations.get("description", "")
    others = len(alerts) - 1
    if others:
        extra = f"(+{others} {'altra allerta' if others == 1 else 'altre allerte'})"
        body = f"{body}\n{extra}" if body else extra

    return NotifyIn(
        title=_clip(title, _TITLE_MAX),
        body=_clip(body, _BODY_MAX) or None,
        tag=tag_for(group.groupKey),
        urgency="high" if critical and group.status == "firing" else "normal",
    )


__all__ = ["Alert", "AlertGroup", "tag_for", "to_notification"]
