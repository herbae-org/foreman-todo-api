from __future__ import annotations

import asyncio


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue[dict]]] = {}

    def subscribe(self, user_id: int) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(user_id, set()).add(queue)
        return queue

    def unsubscribe(self, user_id: int, queue: asyncio.Queue[dict]) -> None:
        subs = self._subscribers.get(user_id)
        if subs:
            subs.discard(queue)
            if not subs:
                del self._subscribers[user_id]

    async def publish(self, user_id: int, event: dict) -> None:
        for queue in self._subscribers.get(user_id, set()).copy():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop event to avoid unbounded memory growth.
                pass

    def reset(self) -> None:
        self._subscribers.clear()

    def subscriber_count(self, user_id: int) -> int:
        return len(self._subscribers.get(user_id, set()))


bus = EventBus()
