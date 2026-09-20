"""Shared entity base for the Carlo Gavazzi EM/ET300."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_NAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_FIRMWARE,
    CONF_MODEL,
    CONF_SERIAL_NUMBER,
    DEFAULT_NAME,
    DOMAIN,
)
from .coordinator import Em300ConfigEntry, Em300Coordinator

MANUFACTURER = "Carlo Gavazzi"


def em300_device_info(entry: Em300ConfigEntry) -> DeviceInfo:
    """Return device-registry info for the meter behind a config entry.

    Everything here is read from the entry rather than from the live device so
    the registry entry is stable across restarts, including while the meter is
    unreachable.
    """
    serial_number = entry.data.get(CONF_SERIAL_NUMBER)
    identifier = serial_number or entry.entry_id

    return DeviceInfo(
        identifiers={(DOMAIN, identifier)},
        manufacturer=MANUFACTURER,
        model=entry.data.get(CONF_MODEL),
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
        serial_number=serial_number,
        sw_version=entry.data.get(CONF_FIRMWARE),
    )


class Em300Entity(CoordinatorEntity[Em300Coordinator]):
    """Base for entities backed by the EM/ET300 coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Em300Coordinator,
        entry: Em300ConfigEntry,
        context: Any = None,
    ) -> None:
        """Store the config entry and attach shared device info."""
        super().__init__(coordinator, context)
        self._config_entry = entry
        self._attr_device_info = em300_device_info(entry)
