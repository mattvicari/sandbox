"""Data fetching and command dispatch for the Jandy TCX add-on's REST API."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientError, ClientSession

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 10


class TCXApiError(Exception):
    """Raised when the add-on's REST API can't be reached or returns an error."""


class TCXClient:
    """Thin wrapper around the add-on's /status and /statecontrol endpoints."""

    def __init__(self, session: ClientSession, host: str, port: int) -> None:
        self._session = session
        self._base_url = f"http://{host}:{port}"

    async def async_get_status(self) -> dict[str, Any]:
        """Fetch the cached controller state (GET /status)."""
        try:
            async with asyncio.timeout(_REQUEST_TIMEOUT):
                async with self._session.get(f"{self._base_url}/status") as resp:
                    resp.raise_for_status()
                    # The add-on returns json.dumps(...) as a plain string body.
                    return await resp.json(content_type=None)
        except (ClientError, TimeoutError) as err:
            raise TCXApiError(f"Error fetching TCX status: {err}") from err

    async def async_send_command(self, namespace: str, desired: dict[str, Any]) -> None:
        """POST a desired-state command (POST /statecontrol)."""
        payload = {"namespace": namespace, "desired": desired}
        try:
            async with asyncio.timeout(_REQUEST_TIMEOUT):
                async with self._session.post(
                    f"{self._base_url}/statecontrol", json=payload
                ) as resp:
                    resp.raise_for_status()
        except (ClientError, TimeoutError) as err:
            raise TCXApiError(f"Error sending TCX command {payload}: {err}") from err


class TCXDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the add-on's /status endpoint on a fixed interval."""

    def __init__(self, hass: HomeAssistant, client: TCXClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="tcx",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.async_get_status()
        except TCXApiError as err:
            raise UpdateFailed(str(err)) from err
