"""Tests for the Modbus transport layer."""

import asyncio

import pytest
from em300_api.client import (
    DEFAULT_TCP_PORT,
    Em300Client,
    Em300SerialClient,
    Em300TcpClient,
    _validate_serial_port,
    framer_type,
)
from em300_api.exception import ModbusException, ModbusPortException
from pymodbus import FramerType


class Response:
    """Stands in for a pymodbus response object."""

    def __init__(self, registers=None, error=False):
        self.registers = registers or []
        self._error = error

    def isError(self):  # noqa: N802 - pymodbus spells it this way
        return self._error


class FakePymodbusClient:
    """Records calls and replays canned responses."""

    def __init__(self, response=None):
        self.response = response
        self.calls: list[dict] = []
        self.connected = False
        self.closed = False

    async def connect(self):
        self.connected = True

    def close(self):
        self.closed = True

    async def read_holding_registers(self, address, count, device_id):
        self.calls.append({"address": address, "count": count, "device_id": device_id})
        return self.response

    async def write_register(self, address, value, device_id):
        self.calls.append({"address": address, "value": value, "device_id": device_id})
        return self.response


def client_with(response, unit=1) -> Em300Client:
    client = Em300Client(unit=unit)
    client.client = FakePymodbusClient(response)
    return client


class TestReads:
    async def test_values_are_keyed_by_absolute_address(self):
        client = client_with(Response([10, 20, 30]))
        assert await client.read_holding_registers(0x0100, 3) == {
            0x0100: 10,
            0x0101: 20,
            0x0102: 30,
        }

    async def test_the_unit_id_is_passed_to_pymodbus(self):
        client = client_with(Response([1]), unit=7)
        await client.read_holding_registers(5, 1)
        assert client.client.calls[0] == {
            "address": 5,
            "count": 1,
            "device_id": 7,
        }

    async def test_a_single_word_read_returns_the_bare_value(self):
        client = client_with(Response([0x0155]))
        assert await client.read_holding_register(0x000B) == 0x0155

    async def test_an_error_response_raises(self):
        # pymodbus signals a rejected read with an exception *response* rather
        # than by raising, so an unchecked result looks like a success.
        client = client_with(Response(error=True))
        with pytest.raises(ModbusException, match="0x0100"):
            await client.read_holding_registers(0x0100, 2)

    async def test_a_missing_response_raises(self):
        client = client_with(None)
        with pytest.raises(ModbusException):
            await client.read_holding_registers(0, 1)

    async def test_a_short_read_raises_rather_than_decoding_garbage(self):
        client = client_with(Response([1, 2]))
        with pytest.raises(ModbusException, match="asked for 4"):
            await client.read_holding_registers(0, 4)

    async def test_read_batch_merges_every_read(self):
        client = client_with(Response([1, 1]))
        values = await client.read_batch([(0, 2), (10, 2)])
        assert set(values) == {0, 1, 10, 11}


class TestWrites:
    async def test_the_payload_is_masked_to_16_bits(self):
        client = client_with(Response())
        await client.write_register(0x1000, 0x1_2345)
        assert client.client.calls[0]["value"] == 0x2345

    async def test_a_rejected_write_raises(self):
        client = client_with(Response(error=True))
        with pytest.raises(ModbusException, match="0x1000"):
            await client.write_register(0x1000, 1)


class TestLocking:
    async def test_transactions_do_not_overlap(self):
        # Modbus is a single request/response link; two interleaved
        # transactions would corrupt each other's frames.
        overlapping = False
        in_flight = 0

        class SlowClient(FakePymodbusClient):
            async def read_holding_registers(self, address, count, device_id):
                nonlocal overlapping, in_flight
                in_flight += 1
                overlapping = overlapping or in_flight > 1
                await asyncio.sleep(0)
                in_flight -= 1
                return Response([0] * count)

        client = Em300Client()
        client.client = SlowClient()

        await asyncio.gather(*(client.read_holding_registers(n, 2) for n in range(10)))

        assert not overlapping


class TestConnectionLifecycle:
    async def test_connect_and_close_reach_pymodbus(self):
        client = client_with(Response())
        await client.connect()
        assert client.connected()
        client.close()
        assert client.client.closed


class TestSerialPortValidation:
    def test_an_existing_port_is_accepted(self, tmp_path):
        port = tmp_path / "ttyUSB0"
        port.touch()
        _validate_serial_port(str(port))

    def test_a_missing_port_is_rejected(self, tmp_path):
        with pytest.raises(ModbusPortException, match="not available"):
            _validate_serial_port(str(tmp_path / "nope"))

    def test_construction_fails_fast_on_a_missing_port(self, tmp_path):
        with pytest.raises(ModbusPortException):
            Em300SerialClient(port=str(tmp_path / "nope"))

    def test_a_windows_port_name_is_rejected_off_windows(self, monkeypatch):
        monkeypatch.setattr("em300_api.client.sys.platform", "win32")
        _validate_serial_port("COM3")
        with pytest.raises(ModbusPortException, match="Windows"):
            _validate_serial_port("/dev/ttyUSB0")


class TestFramerSelection:
    def test_modbus_tcp_is_the_default_framing(self):
        assert framer_type("socket") == FramerType.SOCKET

    def test_rtu_is_selectable_for_transparent_bridges(self):
        assert framer_type("rtu") == FramerType.RTU

    def test_the_name_is_case_insensitive(self):
        assert framer_type("RTU") == FramerType.RTU

    def test_an_unrecognised_name_falls_back_to_modbus_tcp(self):
        assert framer_type("nonsense") == FramerType.SOCKET


class TestTcpClient:
    """pymodbus builds its transport eagerly, so these need a running loop."""

    async def test_the_host_and_default_port_are_used(self):
        client = Em300TcpClient(host="192.0.2.10")
        assert client.client.comm_params.host == "192.0.2.10"
        assert client.client.comm_params.port == DEFAULT_TCP_PORT

    async def test_a_custom_port_is_used(self):
        client = Em300TcpClient(host="192.0.2.10", port=1502)
        assert client.client.comm_params.port == 1502

    async def test_the_unit_id_is_kept(self):
        assert Em300TcpClient(host="192.0.2.10", unit=9).unit == 9
