import json
import queue
import threading
from datetime import datetime

from app.models.notification import Notification


class NotificationBroker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[int, list[queue.Queue]] = {}

    def subscribe(self, user_id: int) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.setdefault(user_id, []).append(q)
        return q

    def unsubscribe(self, user_id: int, q: queue.Queue) -> None:
        with self._lock:
            queues = self._subscribers.get(user_id, [])
            if q in queues:
                queues.remove(q)
            if not queues and user_id in self._subscribers:
                del self._subscribers[user_id]

    def publish(self, user_id: int, event_name: str, payload: dict) -> None:
        with self._lock:
            queues = list(self._subscribers.get(user_id, []))

        for q in queues:
            try:
                q.put_nowait((event_name, payload))
            except queue.Full:
                continue


notification_broker = NotificationBroker()


def notification_to_dict(notification: Notification, unread_count: int | None = None) -> dict:
    if unread_count is None:
        unread_count = (
            Notification.query
            .filter(Notification.user_id == notification.user_id, Notification.is_read.is_(False))
            .count()
        )

    return {
        "id": notification.id,
        "title": notification.title,
        "message": notification.message,
        "link": notification.link,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
        "created_at_label": notification.created_at.strftime("%d/%m/%Y %H:%M") if notification.created_at else "",
        "unread_count": unread_count,
    }


def publish_notification_created(notification: Notification) -> None:
    payload = notification_to_dict(notification)
    notification_broker.publish(notification.user_id, "notification_created", payload)


def sse_pack(event_name: str, payload: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def heartbeat_payload() -> dict:
    return {"ts": datetime.utcnow().isoformat() + "Z"}
