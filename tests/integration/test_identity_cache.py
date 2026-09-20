"""Remembering the identified series, and not leaking the connection."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.carlo_gavazzi_em300.api.exception import ModbusException
from custom_components.carlo_gavazzi_em300.const import (
    CONF_SERIES,
    DOMAIN,
)

from .conftest import TEST_SERIAL, FakeTransport, patch_client, serial_config


class UnidentifiableMeter(FakeTransport):
    """Answers every batched read, but refuses the identification code.

    That single-word read is the one thing that names the model, and it is
    also the one read that can fail on its own: the same word is part of the
    V L3-L1 block, which keeps answering normally.
    """

    async def read_holding_register(self, address):
        raise ModbusException(f"no answer at 0x{address:04X}")


def entry_with(hass, **data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="EM340 A1B2C34",
        unique_id=TEST_SERIAL,
        data={
            **serial_config(),
            "name": "EM340 A1B2C34",
            "model": "EM340",
            "serial_number": TEST_SERIAL,
            **data,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def setup(hass, entry, transport):
    with patch_client(return_value=transport):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def et_only_entities(hass) -> set[str]:
    """Entity keys that only an ET-series meter or an EM330 can populate."""
    registry = er.async_get(hass)
    keys = {
        entry.unique_id.removeprefix(f"{TEST_SERIAL}_")
        for entry in registry.entities.values()
    }
    return keys & {"run_hour_meter", "kwh_neg_l1", "kwh_neg_l2", "kwh_neg_l3"}


class TestRemembering:
    async def test_the_identified_series_is_stored(self, hass):
        entry = entry_with(hass)
        assert CONF_SERIES not in entry.data

        await setup(hass, entry, FakeTransport())

        assert entry.data[CONF_SERIES] == "EM340"

    async def test_storing_it_does_not_loop_the_entry(self, hass):
        # The write happens before the update listener is registered, so it
        # must not trigger a reload.
        entry = entry_with(hass)
        await setup(hass, entry, FakeTransport())

        assert entry.state is ConfigEntryState.LOADED

    async def test_an_unchanged_series_is_not_rewritten(self, hass):
        entry = entry_with(hass, **{CONF_SERIES: "EM340"})
        await setup(hass, entry, FakeTransport())

        assert entry.data[CONF_SERIES] == "EM340"
        assert entry.state is ConfigEntryState.LOADED


class TestFallingBack:
    async def test_a_failed_identification_reuses_the_stored_series(self, hass):
        entry = entry_with(hass, **{CONF_SERIES: "EM340"})

        await setup(hass, entry, UnidentifiableMeter())

        assert entry.runtime_data.device.info.model == "EM340"
        # Without the stored answer the register set would widen back to
        # everything, creating entities an EM340 can only report zero for.
        assert et_only_entities(hass) == set()

    async def test_the_entity_set_is_the_same_either_way(self, hass):
        identified = entry_with(hass)
        await setup(hass, identified, FakeTransport())
        expected = {e.entity_id for e in er.async_get(hass).entities.values()}

        await hass.config_entries.async_remove(identified.entry_id)
        await hass.async_block_till_done()

        degraded = entry_with(hass, **{CONF_SERIES: "EM340"})
        await setup(hass, degraded, UnidentifiableMeter())

        assert {e.entity_id for e in er.async_get(hass).entities.values()} == expected

    async def test_without_a_stored_series_the_full_set_is_used(self, hass):
        # Still the right call: a meter we cannot name should get every
        # entity rather than none of them.
        entry = entry_with(hass)

        await setup(hass, entry, UnidentifiableMeter())

        assert entry.runtime_data.device.info.series is None
        assert et_only_entities(hass)

    async def test_an_unparseable_stored_series_is_ignored(self, hass):
        # Config entry data survives downgrades and hand-editing.
        entry = entry_with(hass, **{CONF_SERIES: "EM999"})

        await setup(hass, entry, UnidentifiableMeter())

        assert entry.runtime_data.device.info.series is None


class TestConnectionIsNotLeaked:
    """Home Assistant retries setup on a timer; a held port never recovers."""

    async def test_a_failed_connect_closes_the_client(self, hass):
        entry = entry_with(hass)
        transport = FakeTransport()
        transport.fail = True

        await setup(hass, entry, transport)

        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert transport.closed

    async def test_a_failed_first_poll_closes_the_client(self, hass):
        entry = entry_with(hass)

        class PollFails(FakeTransport):
            async def read_batch(self, reads):
                raise ModbusException("link dropped")

        transport = PollFails()
        await setup(hass, entry, transport)

        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert transport.closed

    async def test_an_unexpected_error_still_closes_the_client(self, hass):
        entry = entry_with(hass)

        class Exploding(FakeTransport):
            async def read_holding_registers(self, start, length):
                raise RuntimeError("boom")

        transport = Exploding()
        await setup(hass, entry, transport)

        # Home Assistant turns the error into SETUP_ERROR rather than letting
        # it out; what matters here is that the port did not stay open.
        assert entry.state is ConfigEntryState.SETUP_ERROR
        assert transport.closed

    async def test_a_successful_setup_keeps_the_client_open(self, hass):
        entry = entry_with(hass)
        transport = FakeTransport()

        await setup(hass, entry, transport)

        assert entry.state is ConfigEntryState.LOADED
        assert not transport.closed
