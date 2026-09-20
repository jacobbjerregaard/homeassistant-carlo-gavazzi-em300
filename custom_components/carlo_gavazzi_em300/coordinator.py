"""Coordinator for the Carlo Gavazzi EM/ET300 energy meter."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api.device import Em300Device
from .api.exception import Em300Exception
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

#: How many consecutive failures between reconnect attempts. A dropped RS485
#: link does not heal on its own, but retrying on every poll would spam the
#: bus, so a reconnect is attempted on the first failure and then periodically.
_RECONNECT_EVERY = 10


@dataclass
class Em300RuntimeData:
    """Runtime objects shared between the platforms of one config entry."""

    device: Em300Device
    coordinator: Em300Coordinator


#: Config entry whose ``runtime_data`` holds the device and coordinator.
type Em300ConfigEntry = ConfigEntry[Em300RuntimeData]


class Em300Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the meter and expose the decoded registers by name."""

    config_entry: Em300ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: Em300ConfigEntry,
        device: Em300Device,
        scan_interval: int,
    ) -> None:
        """Initialise the coordinator.

        :param hass: Home Assistant instance.
        :param config_entry: The entry this coordinator belongs to.
        :param device: The meter abstraction used for Modbus reads.
        :param scan_interval: Polling interval in seconds.
        """
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.device = device
        self._failure_count = 0

    @property
    def registers(self):
        """The registers currently being polled."""
        return self.device.registers

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and decode every supported register.

        Raising :class:`UpdateFailed` here is enough for both cases Home
        Assistant cares about: during the first refresh it is converted into
        ``ConfigEntryNotReady`` for us, and afterwards it flips the entities to
        unavailable.
        """
        try:
            data = await self.device.read_all()
        except (Em300Exception, OSError, TimeoutError) as err:
            await self._async_try_reconnect()
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="read_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        if not data:
            # Every register was dropped as missing, which means the reads
            # succeeded but returned nothing usable. Surfacing this keeps
            # entities from showing indefinitely stale values.
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="no_data",
            )

        self._failure_count = 0
        return data

    async def _async_try_reconnect(self) -> None:
        """Attempt to re-open the link, at most once every few failures."""
        should_retry = self._failure_count % _RECONNECT_EVERY == 0
        self._failure_count += 1
        if not should_retry:
            return

        try:
            await self.device.connect()
        except Exception:  # noqa: BLE001 - reconnecting is best-effort
            _LOGGER.debug("Reconnect attempt failed", exc_info=True)
