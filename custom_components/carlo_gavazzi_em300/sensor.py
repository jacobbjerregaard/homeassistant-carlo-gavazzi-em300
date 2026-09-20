"""Sensor platform for the Carlo Gavazzi EM/ET300 energy meter."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Em300ConfigEntry, Em300Coordinator
from .entity import Em300Entity
from .entity_descriptions import (
    EM300_SENSOR_DESCRIPTIONS,
    PHASE_SEQUENCE_OPTIONS,
    Em300SensorEntityDescription,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: Em300ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a sensor for every register this meter actually reports.

    The register set was narrowed at setup to what the detected model
    supports, so descriptions for registers this meter does not have never
    become entities.
    """
    coordinator = config_entry.runtime_data.coordinator
    available = {register.name for register in coordinator.registers}

    async_add_entities(
        Em300Sensor(coordinator, config_entry, description)
        for description in EM300_SENSOR_DESCRIPTIONS
        if description.key in available
    )


class Em300Sensor(Em300Entity, SensorEntity):
    """A single decoded register, presented as a sensor."""

    entity_description: Em300SensorEntityDescription

    def __init__(
        self,
        coordinator: Em300Coordinator,
        entry: Em300ConfigEntry,
        description: Em300SensorEntityDescription,
    ) -> None:
        """Initialise the sensor from its description."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{description.key}"

    @property
    def available(self) -> bool:
        """Whether the last poll produced a value for this register."""
        return super().available and (
            self.entity_description.key in (self.coordinator.data or {})
        )

    @property
    def native_value(self) -> Any | None:
        """Return the decoded register value."""
        value = (self.coordinator.data or {}).get(self.entity_description.key)
        if value is None:
            return None

        if self.entity_description.device_class is SensorDeviceClass.ENUM:
            # An out-of-range code would fail HA's option validation, so an
            # unrecognised value is reported as unknown instead.
            return PHASE_SEQUENCE_OPTIONS.get(int(value))

        return value
