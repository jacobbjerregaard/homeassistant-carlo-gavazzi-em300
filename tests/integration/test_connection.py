"""Building a Modbus client from stored config entry data.

This is the one place a config key is mapped onto a transport argument, so a
renamed or mistyped key would silently connect with the wrong settings.
"""

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_HOST, CONF_PORT

from custom_components.carlo_gavazzi_em300.api.client import (
    Em300SerialClient,
    Em300TcpClient,
)
from custom_components.carlo_gavazzi_em300.api.exception import ModbusPortException
from custom_components.carlo_gavazzi_em300.connection import client_from_config
from custom_components.carlo_gavazzi_em300.const import (
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_FRAMER,
    CONF_PARITY,
    CONF_SERIAL_PORT,
    CONF_STOPBITS,
    CONF_TRANSPORT,
    DEFAULT_TCP_PORT,
    Transport,
)


@pytest.fixture
def serial_port(tmp_path):
    """A path that exists, so the serial client will accept it."""
    port = tmp_path / "ttyUSB0"
    port.touch()
    return str(port)


class TestSerial:
    async def test_builds_a_serial_client(self, serial_port):
        client = client_from_config(
            {CONF_TRANSPORT: Transport.SERIAL, CONF_SERIAL_PORT: serial_port}
        )
        assert isinstance(client, Em300SerialClient)

    async def test_serial_settings_reach_pymodbus(self, serial_port):
        client = client_from_config(
            {
                CONF_TRANSPORT: Transport.SERIAL,
                CONF_SERIAL_PORT: serial_port,
                CONF_BAUDRATE: 19200,
                CONF_PARITY: "even",
                CONF_STOPBITS: 2,
                CONF_BYTESIZE: 7,
                CONF_ADDRESS: 3,
            }
        )

        params = client.client.comm_params
        assert params.baudrate == 19200
        # Stored spelled out, handed to pymodbus as its character.
        assert params.parity == "E"
        assert params.stopbits == 2
        assert params.bytesize == 7
        assert client.unit == 3

    async def test_serial_is_the_default_transport(self, serial_port):
        # An entry written before TCP support would have no transport key.
        client = client_from_config({CONF_SERIAL_PORT: serial_port})
        assert isinstance(client, Em300SerialClient)

    async def test_defaults_are_applied_for_missing_settings(self, serial_port):
        client = client_from_config(
            {CONF_TRANSPORT: Transport.SERIAL, CONF_SERIAL_PORT: serial_port}
        )

        params = client.client.comm_params
        assert params.baudrate == 9600
        assert params.parity == "N"
        assert client.unit == 1

    async def test_a_missing_port_is_rejected(self, tmp_path):
        with pytest.raises(ModbusPortException):
            client_from_config(
                {
                    CONF_TRANSPORT: Transport.SERIAL,
                    CONF_SERIAL_PORT: str(tmp_path / "nope"),
                }
            )


class TestTcp:
    async def test_builds_a_tcp_client(self):
        client = client_from_config(
            {CONF_TRANSPORT: Transport.TCP, CONF_HOST: "192.0.2.10"}
        )
        assert isinstance(client, Em300TcpClient)

    async def test_host_port_and_address_reach_pymodbus(self):
        client = client_from_config(
            {
                CONF_TRANSPORT: Transport.TCP,
                CONF_HOST: "192.0.2.10",
                CONF_PORT: 1502,
                CONF_FRAMER: "rtu",
                CONF_ADDRESS: 5,
            }
        )

        assert client.client.comm_params.host == "192.0.2.10"
        assert client.client.comm_params.port == 1502
        assert client.unit == 5

    async def test_the_default_tcp_port_is_used(self):
        client = client_from_config(
            {CONF_TRANSPORT: Transport.TCP, CONF_HOST: "192.0.2.10"}
        )
        assert client.client.comm_params.port == DEFAULT_TCP_PORT
