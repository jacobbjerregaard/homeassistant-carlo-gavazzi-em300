"""The Carlo Gavazzi EM300 Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api.device import Em300Device, Em300DeviceInfo
from .api.exception import Em300Exception
from .api.models import series_from_value
from .connection import client_from_config
from .const import CONF_SERIES, DEFAULT_SCAN_INTERVAL, PLATFORMS
from .coordinator import Em300ConfigEntry, Em300Coordinator, Em300RuntimeData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: Em300ConfigEntry) -> bool:
    """Set up an EM/ET300 meter from a config entry."""
    try:
        client = client_from_config(dict(entry.data))
    except Em300Exception as err:
        # Typically a serial port that is not there right now; worth retrying
        # in case the adapter is plugged back in.
        raise ConfigEntryNotReady(f"Could not open the connection: {err}") from err

    device = Em300Device(client)
    try:
        await device.connect()
        info = await device.identify(
            fallback_series=series_from_value(entry.data.get(CONF_SERIES))
        )
        _async_remember_series(hass, entry, info)

        coordinator = Em300Coordinator(hass, entry, device, _scan_interval(entry))
        await coordinator.async_config_entry_first_refresh()
    except (Em300Exception, OSError, TimeoutError) as err:
        device.close()
        raise ConfigEntryNotReady(f"Could not reach the meter: {err}") from err
    except Exception:
        # Whatever went wrong, the connection must not stay open. Home
        # Assistant retries setup on a timer, and a serial port left held
        # would leak a descriptor -- and block the retry -- every time.
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


def _scan_interval(entry: Em300ConfigEntry) -> int:
    """Return the configured polling interval, options taking precedence."""
    return entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )


def _async_remember_series(
    hass: HomeAssistant, entry: Em300ConfigEntry, info: Em300DeviceInfo
) -> None:
    """Persist a newly identified series so the entity set stays stable.

    Identification is best-effort, so without a remembered answer one failed
    read at setup would hand every register back to the platform and create
    entities this model cannot populate.

    This runs before the update listener is registered below, so writing to
    the entry here cannot trigger a reload. ``async_update_entry`` is a no-op
    when nothing changed, which is the usual case.
    """
    if info.series is None or entry.data.get(CONF_SERIES) == info.series:
        return

    _LOGGER.debug("Remembering identified series %s", info.series)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_SERIES: info.series}
    )


async def _async_update_listener(hass: HomeAssistant, entry: Em300ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
