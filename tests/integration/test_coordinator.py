"""Coordinator behaviour around failures, reconnects and odd register values."""

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.carlo_gavazzi_em300.coordinator import _RECONNECT_EVERY


@pytest.fixture
async def coordinator(hass, config_entry, mock_client):
    """A coordinator attached to a set-up entry."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry.runtime_data.coordinator


class TestFailures:
    async def test_a_read_failure_raises_update_failed(
        self, hass, coordinator, mock_client
    ):
        mock_client.fail = True
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_a_response_with_no_usable_registers_raises(
        self, hass, coordinator, mock_client
    ):
        # Reads succeed but every register is dropped as missing; entities
        # must go unavailable rather than keep showing stale values.
        mock_client.words = {}
        coordinator.device.batch.reads = []

        with pytest.raises(UpdateFailed, match="no_data|usable"):
            await coordinator._async_update_data()

    async def test_the_failure_count_resets_after_a_good_poll(
        self, hass, coordinator, mock_client
    ):
        mock_client.fail = True
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator._failure_count == 1

        mock_client.fail = False
        await coordinator._async_update_data()

        assert coordinator._failure_count == 0


class TestReconnect:
    async def test_the_first_failure_triggers_a_reconnect(
        self, hass, coordinator, mock_client
    ):
        before = mock_client.connected_count
        # Reads are rejected while the link itself still accepts a connect.
        mock_client.words = {}

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

        assert mock_client.connected_count == before + 1

    async def test_reconnects_are_rate_limited(self, hass, coordinator, mock_client):
        # Retrying on every poll would spam a bus that is already down.
        attempts = 0
        original = coordinator.device.connect

        async def counting_connect():
            nonlocal attempts
            attempts += 1
            await original()

        coordinator.device.connect = counting_connect
        mock_client.fail = True

        for _ in range(_RECONNECT_EVERY * 2):
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()

        assert attempts == 2

    async def test_a_failing_reconnect_does_not_mask_the_read_error(
        self, hass, coordinator, mock_client
    ):
        # Reconnecting is best-effort; what surfaces is the read failure, not
        # whatever the reconnect attempt threw.
        mock_client.fail = True

        with pytest.raises(UpdateFailed) as failure:
            await coordinator._async_update_data()

        assert failure.value.translation_key == "read_failed"


class TestPhaseSequenceSensor:
    """The enum sensor maps a raw code onto a declared option."""

    async def test_the_documented_codes_are_mapped(
        self, hass, config_entry, mock_client
    ):
        from custom_components.carlo_gavazzi_em300.sensor import Em300Sensor

        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        coordinator = config_entry.runtime_data.coordinator

        sensor = next(
            Em300Sensor(coordinator, config_entry, description)
            for description in _descriptions()
            if description.key == "phase_sequence"
        )

        coordinator.data["phase_sequence"] = 0
        assert sensor.native_value == "l1_l2_l3"

        coordinator.data["phase_sequence"] = 1
        assert sensor.native_value == "l1_l3_l2"

    async def test_an_undocumented_code_reads_as_unknown(
        self, hass, config_entry, mock_client
    ):
        from custom_components.carlo_gavazzi_em300.sensor import Em300Sensor

        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        coordinator = config_entry.runtime_data.coordinator

        sensor = next(
            Em300Sensor(coordinator, config_entry, description)
            for description in _descriptions()
            if description.key == "phase_sequence"
        )

        # An out-of-range option would fail Home Assistant's own validation.
        coordinator.data["phase_sequence"] = 7
        assert sensor.native_value is None

    async def test_a_register_missing_from_the_poll_reads_as_unknown(
        self, hass, config_entry, mock_client
    ):
        from custom_components.carlo_gavazzi_em300.sensor import Em300Sensor

        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        coordinator = config_entry.runtime_data.coordinator

        sensor = next(
            Em300Sensor(coordinator, config_entry, description)
            for description in _descriptions()
            if description.key == "w_sys"
        )

        coordinator.data.pop("w_sys")
        assert sensor.native_value is None
        assert not sensor.available


def _descriptions():
    from custom_components.carlo_gavazzi_em300.entity_descriptions import (
        EM300_SENSOR_DESCRIPTIONS,
    )

    return EM300_SENSOR_DESCRIPTIONS
