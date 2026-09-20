"""Config and options flow."""

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_ADDRESS, CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResultType

from custom_components.carlo_gavazzi_em300.api.exception import (
    ModbusException,
    ModbusPortException,
)
from custom_components.carlo_gavazzi_em300.const import (
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_FRAMER,
    CONF_MODEL,
    CONF_PARITY,
    CONF_SERIAL_NUMBER,
    CONF_SERIAL_PORT,
    CONF_STOPBITS,
    CONF_TRANSPORT,
    DOMAIN,
    Transport,
)

from .conftest import TEST_PORT, TEST_SERIAL, FakeTransport, patch_client

SERIAL_INPUT = {
    CONF_SERIAL_PORT: TEST_PORT,
    CONF_BAUDRATE: 9600,
    CONF_PARITY: "N",
    CONF_STOPBITS: 1,
    CONF_BYTESIZE: 8,
    CONF_ADDRESS: 1,
    CONF_SCAN_INTERVAL: 30,
}

TCP_INPUT = {
    CONF_HOST: "192.0.2.10",
    CONF_PORT: 502,
    CONF_FRAMER: "socket",
    CONF_ADDRESS: 1,
    CONF_SCAN_INTERVAL: 30,
}


async def start_flow(hass, step: str):
    """Open the flow and pick a transport from the menu."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {"serial", "tcp"}

    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


class TestSerialFlow:
    async def test_a_reachable_meter_creates_an_entry(self, hass, mock_client):
        form = await start_flow(hass, "serial")
        assert form["type"] is FlowResultType.FORM
        assert form["step_id"] == "serial"

        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], SERIAL_INPUT
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == f"EM340 {TEST_SERIAL}"
        assert result["data"][CONF_TRANSPORT] == Transport.SERIAL
        assert result["data"][CONF_SERIAL_PORT] == TEST_PORT

    async def test_what_the_meter_reports_is_stored(self, hass, mock_client):
        form = await start_flow(hass, "serial")
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], SERIAL_INPUT
        )

        assert result["data"][CONF_SERIAL_NUMBER] == TEST_SERIAL
        assert result["data"][CONF_MODEL] == "EM340"
        assert result["data"]["firmware"] == "A3"

    async def test_the_serial_number_becomes_the_unique_id(self, hass, mock_client):
        form = await start_flow(hass, "serial")
        await hass.config_entries.flow.async_configure(form["flow_id"], SERIAL_INPUT)

        entry = hass.config_entries.async_entries(DOMAIN)[0]
        assert entry.unique_id == TEST_SERIAL

    async def test_the_connection_is_closed_again(self, hass, mock_client):
        # Setup opens its own; leaving the probe's connection open would hold
        # the serial port against it.
        form = await start_flow(hass, "serial")
        await hass.config_entries.flow.async_configure(form["flow_id"], SERIAL_INPUT)
        assert mock_client.closed


class TestSerialFlowErrors:
    async def test_an_unreachable_meter_is_reported_on_the_form(
        self, hass, mock_client
    ):
        mock_client.fail = True
        form = await start_flow(hass, "serial")

        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], SERIAL_INPUT
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

    async def test_a_missing_serial_port_is_reported_separately(self, hass):
        with patch_client(side_effect=ModbusPortException("no such port")):
            form = await start_flow(hass, "serial")
            result = await hass.config_entries.flow.async_configure(
                form["flow_id"], SERIAL_INPUT
            )

        assert result["errors"] == {"base": "invalid_port"}

    async def test_the_form_can_be_retried_after_an_error(self, hass, mock_client):
        mock_client.fail = True
        form = await start_flow(hass, "serial")
        failed = await hass.config_entries.flow.async_configure(
            form["flow_id"], SERIAL_INPUT
        )

        mock_client.fail = False
        result = await hass.config_entries.flow.async_configure(
            failed["flow_id"], SERIAL_INPUT
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY

    async def test_the_same_meter_cannot_be_added_twice(
        self, hass, config_entry, mock_client
    ):
        form = await start_flow(hass, "serial")
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], SERIAL_INPUT
        )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"


class TestTcpFlow:
    async def test_a_reachable_gateway_creates_an_entry(self, hass, mock_client):
        form = await start_flow(hass, "tcp")
        assert form["step_id"] == "tcp"

        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], TCP_INPUT
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_TRANSPORT] == Transport.TCP
        assert result["data"][CONF_HOST] == "192.0.2.10"

    async def test_an_unreachable_gateway_is_reported_on_the_form(
        self, hass, mock_client
    ):
        mock_client.fail = True
        form = await start_flow(hass, "tcp")

        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], TCP_INPUT
        )

        assert result["errors"] == {"base": "cannot_connect"}


class TestUniqueIdFallback:
    """Older meters do not implement the serial-number block."""

    @pytest.fixture
    def anonymous_meter(self):
        transport = FakeTransport()
        for offset in range(7):
            transport.words.pop(0x5000 + offset, None)
        return transport

    async def test_a_serial_meter_falls_back_to_port_and_address(
        self, hass, anonymous_meter
    ):
        with patch_client(return_value=anonymous_meter):
            form = await start_flow(hass, "serial")
            await hass.config_entries.flow.async_configure(
                form["flow_id"], SERIAL_INPUT
            )

        entry = hass.config_entries.async_entries(DOMAIN)[0]
        assert entry.unique_id == f"{TEST_PORT}:1"

    async def test_a_tcp_meter_falls_back_to_host_port_and_address(
        self, hass, anonymous_meter
    ):
        with patch_client(return_value=anonymous_meter):
            form = await start_flow(hass, "tcp")
            await hass.config_entries.flow.async_configure(form["flow_id"], TCP_INPUT)

        entry = hass.config_entries.async_entries(DOMAIN)[0]
        assert entry.unique_id == "192.0.2.10:502:1"

    async def test_two_meters_on_one_bus_stay_distinct(self, hass, anonymous_meter):
        with patch_client(return_value=anonymous_meter):
            for address in (1, 2):
                form = await start_flow(hass, "serial")
                result = await hass.config_entries.flow.async_configure(
                    form["flow_id"], {**SERIAL_INPUT, CONF_ADDRESS: address}
                )
                assert result["type"] is FlowResultType.CREATE_ENTRY

        unique_ids = {e.unique_id for e in hass.config_entries.async_entries(DOMAIN)}
        assert unique_ids == {f"{TEST_PORT}:1", f"{TEST_PORT}:2"}


class TestZeroSerialNumber:
    """A meter that implements the serial block but reports zeros.

    This is not the same as a meter that refuses the read: the words come back
    fine, they are just all zero. str.strip() does not remove NULs, so the
    decoded serial used to be a seven-character string that looked perfectly
    valid to every caller.
    """

    @pytest.fixture
    def zero_serial_meter(self):
        transport = FakeTransport()
        for offset in range(7):
            transport.words[0x5000 + offset] = 0
        return transport

    async def test_it_falls_back_to_port_and_address(self, hass, zero_serial_meter):
        with patch_client(return_value=zero_serial_meter):
            form = await start_flow(hass, "serial")
            await hass.config_entries.flow.async_configure(
                form["flow_id"], SERIAL_INPUT
            )

        entry = hass.config_entries.async_entries(DOMAIN)[0]
        assert entry.unique_id == f"{TEST_PORT}:1"

    async def test_no_nuls_leak_into_the_title_or_the_stored_serial(
        self, hass, zero_serial_meter
    ):
        with patch_client(return_value=zero_serial_meter):
            form = await start_flow(hass, "serial")
            result = await hass.config_entries.flow.async_configure(
                form["flow_id"], SERIAL_INPUT
            )

        assert result["data"][CONF_SERIAL_NUMBER] is None
        assert result["title"] == "EM340"
        assert "\x00" not in result["title"]

    async def test_two_such_meters_on_one_bus_stay_distinct(
        self, hass, zero_serial_meter
    ):
        # Both used to collide on a unique id of seven NUL bytes, so the
        # second meter was rejected as already configured.
        with patch_client(return_value=zero_serial_meter):
            for address in (1, 2):
                form = await start_flow(hass, "serial")
                result = await hass.config_entries.flow.async_configure(
                    form["flow_id"], {**SERIAL_INPUT, CONF_ADDRESS: address}
                )
                assert result["type"] is FlowResultType.CREATE_ENTRY

        unique_ids = {e.unique_id for e in hass.config_entries.async_entries(DOMAIN)}
        assert unique_ids == {f"{TEST_PORT}:1", f"{TEST_PORT}:2"}


class TestOptionsFlow:
    async def test_the_poll_interval_can_be_changed(
        self, hass, config_entry, mock_client
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 15}
        )
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert config_entry.options[CONF_SCAN_INTERVAL] == 15


async def test_a_read_failure_during_identification_does_not_abort_setup(
    hass, mock_client
):
    """Identification is best-effort; a partial answer must still configure."""
    mock_client.words.pop(0x0302)  # firmware block

    form = await start_flow(hass, "serial")
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], SERIAL_INPUT
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["firmware"] is None


async def test_a_connection_that_never_answers_is_reported(hass):
    with patch_client(side_effect=ModbusException("timed out")):
        form = await start_flow(hass, "serial")
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], SERIAL_INPUT
        )

    assert result["errors"] == {"base": "cannot_connect"}
