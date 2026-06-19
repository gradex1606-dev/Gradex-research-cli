"""Singleton broadcaster that pushes JSON events to all active WebSocket clients."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket


class DashboardBroadcaster:
    """Fan-out hub for live dashboard events.

    A single instance is shared across all WebSocket connections via
    :meth:`get`.  Use :meth:`reset` in tests to obtain a clean slate.
    """

    _instance: DashboardBroadcaster | None = None

    def __init__(self) -> None:
        self._clients: list[WebSocket] = []
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Singleton helpers
    # ------------------------------------------------------------------

    @classmethod
    def get(cls) -> DashboardBroadcaster:
        """Return the process-wide singleton, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Discard the singleton.  Intended for test isolation only."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self, ws: WebSocket) -> None:
        """Accept *ws* and register it for broadcasts."""
        await ws.accept()
        async with self._lock:
            self._clients.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove *ws* from the broadcast list."""
        async with self._lock:
            self._clients = [c for c in self._clients if c is not ws]

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send *event* as JSON text to every connected client.

        Dead connections are silently removed so they do not prevent
        delivery to healthy clients.
        """
        payload = json.dumps(event)
        async with self._lock:
            live: list[WebSocket] = []
            for client in self._clients:
                try:
                    await client.send_text(payload)
                    live.append(client)
                except Exception:  # noqa: BLE001 — dead connection, discard silently
                    pass
            self._clients = live
