"""Sensor entity descriptions for the Carlo Gavazzi EM/ET300.

Each description maps one register -- identified by the ``name`` the API layer
decodes it under -- to the metadata Home Assistant needs to present it. The
description ``key`` is that register name, and doubles as the translation key,
so display names live in ``strings.json`` rather than here.

The meter reports each quantity per phase and as a system aggregate. Only the
system aggregates are enabled by default; the per-phase breakdown is created
but hidden, so a typical installation gets a handful of useful entities instead
of forty-odd, without anyone having to edit YAML to get the rest.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactiveEnergy,
    UnitOfReactivePower,
    UnitOfTime,
)


@dataclass(frozen=True, kw_only=True)
class Em300SensorEntityDescription(SensorEntityDescription):
    """Describes an EM/ET300 sensor entity."""


def _measurement(
    key: str,
    device_class: SensorDeviceClass,
    unit: str | None,
    *,
    default: bool = False,
) -> Em300SensorEntityDescription:
    """Describe an instantaneous reading: a voltage, current or power."""
    return Em300SensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=device_class,
        native_unit_of_measurement=unit,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=default,
        suggested_display_precision=2,
    )


def _total(
    key: str,
    device_class: SensorDeviceClass,
    unit: str,
    *,
    default: bool = False,
) -> Em300SensorEntityDescription:
    """Describe a cumulative meter reading that climbs or is reset."""
    return Em300SensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=device_class,
        native_unit_of_measurement=unit,
        # The partial and tariff meters can be reset from the meter's own menu;
        # TOTAL_INCREASING lets the statistics engine absorb that as a reset
        # rather than as a huge negative delta.
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=default,
        suggested_display_precision=1,
    )


VOLT = UnitOfElectricPotential.VOLT
AMPERE = UnitOfElectricCurrent.AMPERE
WATT = UnitOfPower.WATT
VOLT_AMPERE = UnitOfApparentPower.VOLT_AMPERE
VAR = UnitOfReactivePower.VOLT_AMPERE_REACTIVE
HERTZ = UnitOfFrequency.HERTZ
KWH = UnitOfEnergy.KILO_WATT_HOUR
KVARH = UnitOfReactiveEnergy.KILO_VOLT_AMPERE_REACTIVE_HOUR
HOURS = UnitOfTime.HOURS

EM300_SENSOR_DESCRIPTIONS: tuple[Em300SensorEntityDescription, ...] = (
    # --- System aggregates (enabled by default) ---------------------------
    _measurement("v_ln_sys", SensorDeviceClass.VOLTAGE, VOLT, default=True),
    _measurement("v_ll_sys", SensorDeviceClass.VOLTAGE, VOLT, default=True),
    _measurement("w_sys", SensorDeviceClass.POWER, WATT, default=True),
    _measurement("va_sys", SensorDeviceClass.APPARENT_POWER, VOLT_AMPERE, default=True),
    _measurement("var_sys", SensorDeviceClass.REACTIVE_POWER, VAR, default=True),
    # Power factor is dimensionless; the device class supplies the meaning.
    _measurement("pf_sys", SensorDeviceClass.POWER_FACTOR, None, default=True),
    _measurement("hz", SensorDeviceClass.FREQUENCY, HERTZ, default=True),
    # --- Energy totalizers (enabled by default) ---------------------------
    _total("kwh_pos_tot", SensorDeviceClass.ENERGY, KWH, default=True),
    _total("kwh_neg_tot", SensorDeviceClass.ENERGY, KWH, default=True),
    _total("kvarh_pos_tot", SensorDeviceClass.REACTIVE_ENERGY, KVARH, default=True),
    _total("kvarh_neg_tot", SensorDeviceClass.REACTIVE_ENERGY, KVARH, default=True),
    # --- Demand power -----------------------------------------------------
    _measurement("w_dmd", SensorDeviceClass.POWER, WATT),
    _measurement("w_dmd_peak", SensorDeviceClass.POWER, WATT),
    # --- Per-phase voltage ------------------------------------------------
    _measurement("v_l1_n", SensorDeviceClass.VOLTAGE, VOLT),
    _measurement("v_l2_n", SensorDeviceClass.VOLTAGE, VOLT),
    _measurement("v_l3_n", SensorDeviceClass.VOLTAGE, VOLT),
    _measurement("v_l1_l2", SensorDeviceClass.VOLTAGE, VOLT),
    _measurement("v_l2_l3", SensorDeviceClass.VOLTAGE, VOLT),
    _measurement("v_l3_l1", SensorDeviceClass.VOLTAGE, VOLT),
    # --- Per-phase current ------------------------------------------------
    _measurement("a_l1", SensorDeviceClass.CURRENT, AMPERE),
    _measurement("a_l2", SensorDeviceClass.CURRENT, AMPERE),
    _measurement("a_l3", SensorDeviceClass.CURRENT, AMPERE),
    # --- Per-phase power --------------------------------------------------
    _measurement("w_l1", SensorDeviceClass.POWER, WATT),
    _measurement("w_l2", SensorDeviceClass.POWER, WATT),
    _measurement("w_l3", SensorDeviceClass.POWER, WATT),
    _measurement("va_l1", SensorDeviceClass.APPARENT_POWER, VOLT_AMPERE),
    _measurement("va_l2", SensorDeviceClass.APPARENT_POWER, VOLT_AMPERE),
    _measurement("va_l3", SensorDeviceClass.APPARENT_POWER, VOLT_AMPERE),
    _measurement("var_l1", SensorDeviceClass.REACTIVE_POWER, VAR),
    _measurement("var_l2", SensorDeviceClass.REACTIVE_POWER, VAR),
    _measurement("var_l3", SensorDeviceClass.REACTIVE_POWER, VAR),
    _measurement("pf_l1", SensorDeviceClass.POWER_FACTOR, None),
    _measurement("pf_l2", SensorDeviceClass.POWER_FACTOR, None),
    _measurement("pf_l3", SensorDeviceClass.POWER_FACTOR, None),
    # --- Partial, per-phase and tariff energy meters ----------------------
    _total("kwh_pos_partial", SensorDeviceClass.ENERGY, KWH),
    _total("kvarh_pos_partial", SensorDeviceClass.REACTIVE_ENERGY, KVARH),
    _total("kwh_pos_l1", SensorDeviceClass.ENERGY, KWH),
    _total("kwh_pos_l2", SensorDeviceClass.ENERGY, KWH),
    _total("kwh_pos_l3", SensorDeviceClass.ENERGY, KWH),
    _total("kwh_pos_t1", SensorDeviceClass.ENERGY, KWH),
    _total("kwh_pos_t2", SensorDeviceClass.ENERGY, KWH),
    _total("kwh_neg_l1", SensorDeviceClass.ENERGY, KWH),
    _total("kwh_neg_l2", SensorDeviceClass.ENERGY, KWH),
    _total("kwh_neg_l3", SensorDeviceClass.ENERGY, KWH),
    # --- Diagnostics ------------------------------------------------------
    Em300SensorEntityDescription(
        key="run_hour_meter",
        translation_key="run_hour_meter",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    # 0 means L1-L2-L3, 1 means L1-L3-L2; only meaningful on 3-phase systems.
    Em300SensorEntityDescription(
        key="phase_sequence",
        translation_key="phase_sequence",
        device_class=SensorDeviceClass.ENUM,
        options=["l1_l2_l3", "l1_l3_l2"],
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)

#: Raw phase-sequence register value -> the enum option reported to HA.
PHASE_SEQUENCE_OPTIONS: dict[int, str] = {0: "l1_l2_l3", 1: "l1_l3_l2"}
