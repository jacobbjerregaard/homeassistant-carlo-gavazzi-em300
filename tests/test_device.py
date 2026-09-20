"""Tests for the device abstraction: identification and polling."""

import pytest
from em300_api.device import Em300Device, Em300DeviceInfo
from em300_api.exception import ModbusException
from em300_api.models import Series
from em300_api.register_map import (
    EM300_REGISTERS,
    REG_CG_IDENTIFICATION,
    REG_SERIAL_NUMBER,
)

SERIAL = "A1B2C34"


class FakeClient:
    """A client backed by an in-memory word map.

    Reads outside the populated range raise, the way a meter answers a request
    for an address it does not implement.
    """

    def __init__(self, words: dict[int, int], unit: int = 1) -> None:
        self.words = words
        self.unit = unit
        self.reads: list[tuple[int, int]] = []
        self.closed = False
        self.connects = 0

    async def connect(self) -> None:
        self.connects += 1

    def close(self) -> None:
        self.closed = True

    async def read_holding_registers(self, start, length):
        self.reads.append((start, length))
        addresses = range(start, start + length)
        if any(address not in self.words for address in addresses):
            raise ModbusException(f"illegal data address at 0x{start:04X}")
        return {address: self.words[address] for address in addresses}

    async def read_holding_register(self, address):
        return (await self.read_holding_registers(address, 1))[address]

    async def read_batch(self, reads):
        values = {}
        for start, length in reads:
            values.update(await self.read_holding_registers(start, length))
        return values


def meter_words(identification_code=341, serial=SERIAL, firmware=(0, 3)):
    """Build the word map of a meter reporting zero for every measurement."""
    words = {
        address: 0 for register in EM300_REGISTERS for address in register.addresses
    }

    if identification_code is not None:
        # Read on its own this word is the identification code; read as part
        # of V L3-L1 it is that value's high word.
        words[REG_CG_IDENTIFICATION.address] = identification_code
    if serial is not None:
        for offset, char in enumerate(serial):
            words[REG_SERIAL_NUMBER.address + offset] = ord(char)
    if firmware is not None:
        words[0x0302], words[0x0303] = firmware
    return words


async def identified(**kwargs) -> tuple[Em300Device, Em300DeviceInfo]:
    device = Em300Device(FakeClient(meter_words(**kwargs)))
    return device, await device.identify()


class TestIdentify:
    async def test_reports_serial_series_and_firmware(self):
        _, info = await identified()
        assert info.serial_number == SERIAL
        assert info.series is Series.EM340
        assert info.identification_code == 341
        assert info.firmware == "A3"

    async def test_firmware_combines_version_letter_and_revision(self):
        # Version 0 means "A", 1 means "B"; revision 0 means "0".
        _, info = await identified(firmware=(1, 0))
        assert info.firmware == "B0"

    async def test_model_is_the_detected_series(self):
        _, info = await identified(identification_code=345)
        assert info.series is Series.ET340
        assert info.model == "ET340"

    async def test_an_unknown_code_still_produces_a_model_name(self):
        _, info = await identified(identification_code=999)
        assert info.series is None
        assert "999" in info.model

    async def test_identification_is_stored_on_the_device(self):
        device, info = await identified()
        assert device.info is info


class TestDegradedIdentification:
    """Identification must never block setup on its own."""

    async def test_a_meter_without_a_serial_number_block(self):
        words = meter_words(serial=None)
        for offset in range(7):
            words.pop(REG_SERIAL_NUMBER.address + offset, None)

        info = await Em300Device(FakeClient(words)).identify()

        assert info.serial_number is None
        assert info.series is Series.EM340

    async def test_a_meter_without_a_firmware_block(self):
        words = meter_words()
        del words[0x0302], words[0x0303]

        info = await Em300Device(FakeClient(words)).identify()

        assert info.firmware is None
        assert info.serial_number == SERIAL

    async def test_a_meter_that_refuses_the_identification_code(self):
        words = meter_words(identification_code=None)
        del words[REG_CG_IDENTIFICATION.address]

        info = await Em300Device(FakeClient(words)).identify()

        assert info.identification_code is None
        assert info.series is None


class TestRegisterFiltering:
    async def test_an_em340_drops_the_et_only_registers(self):
        device, _ = await identified(identification_code=341)
        names = {register.name for register in device.registers}
        assert "run_hour_meter" not in names
        assert "kwh_neg_l1" not in names
        assert "w_sys" in names

    async def test_an_et340_keeps_them(self):
        device, _ = await identified(identification_code=345)
        names = {register.name for register in device.registers}
        assert {"run_hour_meter", "kwh_neg_l1"} <= names

    async def test_an_unidentified_meter_keeps_every_register(self):
        device, _ = await identified(identification_code=999)
        assert len(device.registers) == len(EM300_REGISTERS)

    async def test_the_batch_is_replanned_after_filtering(self):
        device, _ = await identified(identification_code=341)
        planned = device.batch.addresses
        for register in device.registers:
            assert set(register.addresses) <= planned


class TestReadAll:
    async def test_decodes_every_polled_register(self):
        device, _ = await identified()
        data = await device.read_all()
        assert set(data) == {r.name for r in device.registers}

    async def test_applies_the_value_weight(self):
        words = meter_words()
        words[0x0000], words[0x0001] = 2301, 0  # V L1-N, LSW first
        device = Em300Device(FakeClient(words))
        await device.identify()

        assert (await device.read_all())["v_l1_n"] == 230.1

    async def test_a_failing_read_propagates(self):
        device, _ = await identified()
        device.client.words.clear()
        with pytest.raises(ModbusException):
            await device.read_all()

    async def test_polling_stays_within_the_frame_limit(self):
        device, _ = await identified()
        device.client.reads.clear()
        await device.read_all()
        assert all(length <= 20 for _, length in device.client.reads)


class TestTransportPassthrough:
    async def test_connect_and_close_reach_the_client(self):
        client = FakeClient(meter_words())
        device = Em300Device(client)

        await device.connect()
        device.close()

        assert client.connects == 1
        assert client.closed

    async def test_unit_comes_from_the_client(self):
        assert Em300Device(FakeClient({}, unit=7)).unit == 7
