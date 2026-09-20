"""Tests pinning the register map to the published protocol.

The addresses and value weights below are transcribed independently from
*EM300 Series and ET300 Series Communication Protocol* v2 rev 17, table 2.4-1,
so a typo in the map fails here rather than producing plausible-looking but
wrong readings on real hardware.
"""

import pytest
from em300_api.models import Em300Register, RegisterDataType, Series
from em300_api.register_map import (
    CG_IDENTIFICATION_CODES,
    EM300_IDENTITY_REGISTERS,
    EM300_REGISTERS,
    REG_CG_IDENTIFICATION,
    REG_SERIAL_NUMBER,
    series_for_identification_code,
)

I32 = RegisterDataType.INT32
I16 = RegisterDataType.INT16

# (name, physical address, data type, value weight) straight from table 2.4-1.
TABLE_2_4_1 = [
    ("v_l1_n", 0x0000, I32, 10),
    ("v_l2_n", 0x0002, I32, 10),
    ("v_l3_n", 0x0004, I32, 10),
    ("v_l1_l2", 0x0006, I32, 10),
    ("v_l2_l3", 0x0008, I32, 10),
    ("v_l3_l1", 0x000A, I32, 10),
    ("a_l1", 0x000C, I32, 1000),
    ("a_l2", 0x000E, I32, 1000),
    ("a_l3", 0x0010, I32, 1000),
    ("w_l1", 0x0012, I32, 10),
    ("w_l2", 0x0014, I32, 10),
    ("w_l3", 0x0016, I32, 10),
    ("va_l1", 0x0018, I32, 10),
    ("va_l2", 0x001A, I32, 10),
    ("va_l3", 0x001C, I32, 10),
    ("var_l1", 0x001E, I32, 10),
    ("var_l2", 0x0020, I32, 10),
    ("var_l3", 0x0022, I32, 10),
    ("v_ln_sys", 0x0024, I32, 10),
    ("v_ll_sys", 0x0026, I32, 10),
    ("w_sys", 0x0028, I32, 10),
    ("va_sys", 0x002A, I32, 10),
    ("var_sys", 0x002C, I32, 10),
    ("pf_l1", 0x002E, I16, 1000),
    ("pf_l2", 0x002F, I16, 1000),
    ("pf_l3", 0x0030, I16, 1000),
    ("pf_sys", 0x0031, I16, 1000),
    ("phase_sequence", 0x0032, I16, None),
    ("hz", 0x0033, I16, 10),
    ("kwh_pos_tot", 0x0034, I32, 10),
    ("kvarh_pos_tot", 0x0036, I32, 10),
    ("w_dmd", 0x0038, I32, 10),
    ("w_dmd_peak", 0x003A, I32, 10),
    ("kwh_pos_partial", 0x003C, I32, 10),
    ("kvarh_pos_partial", 0x003E, I32, 10),
    ("kwh_pos_l1", 0x0040, I32, 10),
    ("kwh_pos_l2", 0x0042, I32, 10),
    ("kwh_pos_l3", 0x0044, I32, 10),
    ("kwh_pos_t1", 0x0046, I32, 10),
    ("kwh_pos_t2", 0x0048, I32, 10),
    ("kwh_neg_tot", 0x004E, I32, 10),
    ("kvarh_neg_tot", 0x0050, I32, 10),
    ("run_hour_meter", 0x005A, I32, 100),
    ("kwh_neg_l1", 0x0060, I32, 10),
    ("kwh_neg_l2", 0x0062, I32, 10),
    ("kwh_neg_l3", 0x0064, I32, 10),
]

BY_NAME: dict[str, Em300Register] = {r.name: r for r in EM300_REGISTERS}


@pytest.mark.parametrize(
    ("name", "address", "data_type", "scale"),
    TABLE_2_4_1,
    ids=[row[0] for row in TABLE_2_4_1],
)
def test_register_matches_the_protocol_table(name, address, data_type, scale):
    register = BY_NAME[name]
    assert register.address == address
    assert register.data_type is data_type
    assert register.scale == scale


def test_the_map_holds_exactly_the_transcribed_table():
    assert set(BY_NAME) == {row[0] for row in TABLE_2_4_1}


def test_no_ieee754_registers_exist():
    # Section 2.1 lists IEEE754 as a format, but no register in the EM/ET300
    # map uses it; an earlier map invented nine such registers.
    assert not hasattr(RegisterDataType, "IEEE754")


def test_register_names_are_unique():
    names = [register.name for register in EM300_REGISTERS]
    assert len(names) == len(set(names))


def test_no_two_registers_claim_the_same_word():
    seen: dict[int, str] = {}
    for register in EM300_REGISTERS:
        for address in register.addresses:
            assert address not in seen, (
                f"0x{address:04X} claimed by both {seen.get(address)} "
                f"and {register.name}"
            )
            seen[address] = register.name


def test_unavailable_registers_are_excluded():
    # Rows the protocol marks "Not available, value =0" would only ever
    # produce a sensor stuck at zero.
    excluded = {0x004A, 0x004C, 0x0052, 0x0054, 0x0056, 0x0058, 0x005C, 0x005E}
    claimed = {
        address for register in EM300_REGISTERS for address in register.addresses
    }
    assert claimed.isdisjoint(excluded)


class TestSeriesRestrictions:
    def test_run_hour_meter_is_et_and_em330_only(self):
        register = BY_NAME["run_hour_meter"]
        assert register.supported_by(Series.ET340)
        assert register.supported_by(Series.EM330)
        assert not register.supported_by(Series.EM340)

    @pytest.mark.parametrize("name", ["kwh_neg_l1", "kwh_neg_l2", "kwh_neg_l3"])
    def test_negative_per_phase_energy_is_et_only(self, name):
        register = BY_NAME[name]
        assert register.supported_by(Series.ET340)
        assert not register.supported_by(Series.EM330)
        assert not register.supported_by(Series.EM340)

    def test_an_em340_drops_only_the_restricted_registers(self):
        supported = [r.name for r in EM300_REGISTERS if r.supported_by(Series.EM340)]
        assert set(BY_NAME) - set(supported) == {
            "run_hour_meter",
            "kwh_neg_l1",
            "kwh_neg_l2",
            "kwh_neg_l3",
        }


class TestIdentity:
    def test_serial_number_is_seven_ascii_words(self):
        assert REG_SERIAL_NUMBER.address == 0x5000
        assert REG_SERIAL_NUMBER.length == 7
        assert REG_SERIAL_NUMBER.data_type is RegisterDataType.STRING

    def test_identification_code_must_be_read_on_its_own(self):
        # Its word doubles as the high word of V L3-L1 (0x000A, two words).
        assert REG_CG_IDENTIFICATION.address == 0x000B
        assert REG_CG_IDENTIFICATION.standalone
        assert 0x000B in set(BY_NAME["v_l3_l1"].addresses)

    def test_identity_registers_are_not_polled(self):
        polled = {register.name for register in EM300_REGISTERS}
        for register in EM300_IDENTITY_REGISTERS:
            assert register.name not in polled

    def test_version_and_revision_codes(self):
        by_name = {r.name: r for r in EM300_IDENTITY_REGISTERS}
        assert by_name["version_code"].address == 0x0302
        assert by_name["revision_code"].address == 0x0303


class TestSeriesDetection:
    @pytest.mark.parametrize(
        ("code", "series"),
        [
            (331, Series.EM330),
            (332, Series.EM330),
            (335, Series.ET330),
            (336, Series.ET330),
            (341, Series.EM340),
            (345, Series.ET340),
            (346, Series.EM341),
            (355, Series.EM331),
        ],
    )
    def test_documented_codes_map_to_their_series(self, code, series):
        assert series_for_identification_code(code) is series

    def test_an_unknown_code_has_no_series(self):
        assert series_for_identification_code(9999) is None

    def test_a_missing_code_has_no_series(self):
        assert series_for_identification_code(None) is None

    def test_every_series_is_reachable_from_some_code(self):
        assert set(CG_IDENTIFICATION_CODES.values()) == set(Series)
