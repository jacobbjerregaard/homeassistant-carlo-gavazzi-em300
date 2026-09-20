"""The Carlo Gavazzi EM300 Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api.device import Em300Device
from .api.exception import Em300Exception
from .connection import client_from_config
from .const import DEFAULT_SCAN_INTERVAL, PLATFORMS
from .coordinator import Em300ConfigEntry, Em300Coordinator, Em300RuntimeData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: Em300ConfigEntry) -> bool:
    """Set up an EM/ET300 meter from a config entry."""
    try:
        client = client_from_config(dict(entry.data))
        device = Em300Device(client)
        await device.connect()
        await device.identify()
    except (Em300Exception, OSError, TimeoutError) as err:
        raise ConfigEntryNotReady(f"Could not reach the meter: {err}") from err

    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    coordinator = Em300Coordinator(hass, entry, device, scan_interval)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        device.close()
        raise

    entry.runtime_data = Em300RuntimeData(device=device, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Em300ConfigEntry) -> bool:
    """Unload a config entry and close its Modbus connection."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    entry.runtime_data.device.close()
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: Em300ConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
