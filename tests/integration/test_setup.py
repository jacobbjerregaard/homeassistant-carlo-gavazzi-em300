"""Config entry setup, polling and unload."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.helpers import entity_registry as er

from .conftest import TEST_SERIAL


async def setup_entry(hass, config_entry) -> bool:
    result = await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return result


class TestSetup:
    async def test_entry_loads(self, hass, config_entry, mock_client):
        assert await setup_entry(hass, config_entry)
        assert config_entry.state is ConfigEntryState.LOADED

    async def test_the_meter_is_identified_at_setup(
        self, hass, config_entry, mock_client
    ):
        await setup_entry(hass, config_entry)
        info = config_entry.runtime_data.device.info
        assert info.serial_number == TEST_SERIAL
        assert info.model == "EM340"
        assert info.firmware == "A3"

    async def test_an_unreachable_meter_is_retried_later(
        self, hass, config_entry, mock_client
    ):
        mock_client.fail = True
        await setup_entry(hass, config_entry)
        assert config_entry.state is ConfigEntryState.SETUP_RETRY

    async def test_unload_closes_the_connection(self, hass, config_entry, mock_client):
        await setup_entry(hass, config_entry)

        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()

        assert config_entry.state is ConfigEntryState.NOT_LOADED
        assert mock_client.closed


class TestSensors:
    async def test_system_sensors_are_created_and_decoded(
        self, hass, config_entry, mock_client
    ):
        await setup_entry(hass, config_entry)

        # 2301 with a Volt*10 weight is 230.1 V.
        assert hass.states.get("sensor.em340_a1b2c34_voltage_l_n").state == "230.1"
        # 11500 with a Watt*10 weight is 1150 W.
        assert hass.states.get("sensor.em340_a1b2c34_active_power").state == "1150.0"
        assert hass.states.get("sensor.em340_a1b2c34_frequency").state == "50.0"
        assert hass.states.get("sensor.em340_a1b2c34_imported_energy").state == "1234.5"

    async def test_per_phase_sensors_are_disabled_by_default(
        self, hass, config_entry, mock_client
    ):
        await setup_entry(hass, config_entry)
        assert hass.states.get("sensor.em340_a1b2c34_current_l1") is None

    async def test_et_only_registers_produce_no_entities_on_an_em340(
        self, hass, config_entry, mock_client
    ):
        await setup_entry(hass, config_entry)

        registry = er.async_get(hass)
        keys = {
            entry.unique_id.removeprefix(f"{TEST_SERIAL}_")
            for entry in registry.entities.values()
        }

        assert "w_sys" in keys
        # Documented as ET-only or ET/EM330-only; an EM340 reports zero.
        assert keys.isdisjoint(
            {"run_hour_meter", "kwh_neg_l1", "kwh_neg_l2", "kwh_neg_l3"}
        )

    async def test_sensors_go_unavailable_when_the_link_drops(
        self, hass, config_entry, mock_client
    ):
        await setup_entry(hass, config_entry)
        mock_client.fail = True

        await config_entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()

        assert (
            hass.states.get("sensor.em340_a1b2c34_active_power").state == "unavailable"
        )


class TestOptions:
    async def test_changing_the_poll_interval_reloads_the_entry(
        self, hass, config_entry, mock_client
    ):
        await setup_entry(hass, config_entry)

        hass.config_entries.async_update_entry(
            config_entry, options={CONF_SCAN_INTERVAL: 5}
        )
        await hass.async_block_till_done()

        assert config_entry.state is ConfigEntryState.LOADED
        interval = config_entry.runtime_data.coordinator.update_interval
        assert interval.total_seconds() == 5
