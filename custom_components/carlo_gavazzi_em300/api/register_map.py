"""Curated EM/ET300 register map.

Transcribed from *EM300 Series and ET300 Series Communication Protocol*,
version 2 revision 17 (July 5, 2021). Addresses are the protocol's "physical
address" column -- the word address placed on the wire -- so they are handed to
pymodbus unchanged. The "Modicom address" column plays no part here.

The polled set comes from **table 2.4-1** (instantaneous variables and meters,
grouped by variable type), a contiguous block from ``0x0000`` to ``0x0064``.
Table 2.6-1 exposes the same measurements again, grouped by phase, at
``0x00F6`` onwards; either block may be read, and this integration uses the
former because it is the primary table and is present across the whole range.

Deliberately excluded:

* Rows the protocol marks "Not available, value =0" (the t3-t8 tariff meters,
  the negative partial totalizers, the kVAh meters and the THD registers).
* The 3-decimal totalizers of tables 2.5-1 and 2.5-2. Those depend on the
  manufacturing date ("only EM340/EM330 manufactured from October 1st 2018")
  rather than on the model, and reading an address a meter does not implement
  raises an illegal-data-address exception that would fail the whole batch.
  There is no way to detect support short of probing, so they stay out.
"""

from __future__ import annotations

from .models import (
    ALL_SERIES,
    ET_SERIES,
    ET_SERIES_AND_EM330,
    Em300Register,
    RegisterDataType,
    Series,
)

# --- Value weights (table 2.4-1 "Notes" column) -----------------------------
# The raw integer is divided by these to reach the engineering unit.
WEIGHT_VOLT = 10
WEIGHT_AMPERE = 1000
WEIGHT_WATT = 10
WEIGHT_VA = 10
WEIGHT_VAR = 10
WEIGHT_PF = 1000
WEIGHT_HZ = 10
WEIGHT_KWH = 10
WEIGHT_KVARH = 10
WEIGHT_HOURS = 100


def _i32(
    name: str,
    address: int,
    scale: float | None,
    series: frozenset[Series] = ALL_SERIES,
) -> Em300Register:
    """Build one of the INT32 measurement registers that dominate the map."""
    return Em300Register(
        name=name,
        address=address,
        data_type=RegisterDataType.INT32,
        scale=scale,
        series=series,
    )


def _i16(name: str, address: int, scale: float | None) -> Em300Register:
    """Build one of the four INT16 registers in table 2.4-1."""
    return Em300Register(
        name=name,
        address=address,
        data_type=RegisterDataType.INT16,
        scale=scale,
    )


# --- Table 2.4-1: phase voltages --------------------------------------------
REG_V_L1_N = _i32("v_l1_n", 0x0000, WEIGHT_VOLT)
REG_V_L2_N = _i32("v_l2_n", 0x0002, WEIGHT_VOLT)
REG_V_L3_N = _i32("v_l3_n", 0x0004, WEIGHT_VOLT)
REG_V_L1_L2 = _i32("v_l1_l2", 0x0006, WEIGHT_VOLT)
REG_V_L2_L3 = _i32("v_l2_l3", 0x0008, WEIGHT_VOLT)
REG_V_L3_L1 = _i32("v_l3_l1", 0x000A, WEIGHT_VOLT)

# --- Table 2.4-1: phase currents --------------------------------------------
REG_A_L1 = _i32("a_l1", 0x000C, WEIGHT_AMPERE)
REG_A_L2 = _i32("a_l2", 0x000E, WEIGHT_AMPERE)
REG_A_L3 = _i32("a_l3", 0x0010, WEIGHT_AMPERE)

# --- Table 2.4-1: per-phase power -------------------------------------------
REG_W_L1 = _i32("w_l1", 0x0012, WEIGHT_WATT)
REG_W_L2 = _i32("w_l2", 0x0014, WEIGHT_WATT)
REG_W_L3 = _i32("w_l3", 0x0016, WEIGHT_WATT)
REG_VA_L1 = _i32("va_l1", 0x0018, WEIGHT_VA)
REG_VA_L2 = _i32("va_l2", 0x001A, WEIGHT_VA)
REG_VA_L3 = _i32("va_l3", 0x001C, WEIGHT_VA)
REG_VAR_L1 = _i32("var_l1", 0x001E, WEIGHT_VAR)
REG_VAR_L2 = _i32("var_l2", 0x0020, WEIGHT_VAR)
REG_VAR_L3 = _i32("var_l3", 0x0022, WEIGHT_VAR)

# --- Table 2.4-1: system aggregates -----------------------------------------
REG_V_LN_SYS = _i32("v_ln_sys", 0x0024, WEIGHT_VOLT)
REG_V_LL_SYS = _i32("v_ll_sys", 0x0026, WEIGHT_VOLT)
REG_W_SYS = _i32("w_sys", 0x0028, WEIGHT_WATT)
REG_VA_SYS = _i32("va_sys", 0x002A, WEIGHT_VA)
REG_VAR_SYS = _i32("var_sys", 0x002C, WEIGHT_VAR)

# Power factor and frequency are the only single-word measurements in the
# table. Negative PF corresponds to exported active power.
REG_PF_L1 = _i16("pf_l1", 0x002E, WEIGHT_PF)
REG_PF_L2 = _i16("pf_l2", 0x002F, WEIGHT_PF)
REG_PF_L3 = _i16("pf_l3", 0x0030, WEIGHT_PF)
REG_PF_SYS = _i16("pf_sys", 0x0031, WEIGHT_PF)

# 0 => L1-L2-L3 sequence, 1 => L1-L3-L2. Meaningful only on 3-phase systems.
REG_PHASE_SEQUENCE = _i16("phase_sequence", 0x0032, None)
REG_HZ = _i16("hz", 0x0033, WEIGHT_HZ)

# --- Table 2.4-1: energy totalizers and demand ------------------------------
REG_KWH_POS_TOT = _i32("kwh_pos_tot", 0x0034, WEIGHT_KWH)
REG_KVARH_POS_TOT = _i32("kvarh_pos_tot", 0x0036, WEIGHT_KVARH)
REG_W_DMD = _i32("w_dmd", 0x0038, WEIGHT_WATT)
REG_W_DMD_PEAK = _i32("w_dmd_peak", 0x003A, WEIGHT_WATT)
REG_KWH_POS_PARTIAL = _i32("kwh_pos_partial", 0x003C, WEIGHT_KWH)
REG_KVARH_POS_PARTIAL = _i32("kvarh_pos_partial", 0x003E, WEIGHT_KVARH)
REG_KWH_POS_L1 = _i32("kwh_pos_l1", 0x0040, WEIGHT_KWH)
REG_KWH_POS_L2 = _i32("kwh_pos_l2", 0x0042, WEIGHT_KWH)
REG_KWH_POS_L3 = _i32("kwh_pos_l3", 0x0044, WEIGHT_KWH)
REG_KWH_POS_T1 = _i32("kwh_pos_t1", 0x0046, WEIGHT_KWH)
REG_KWH_POS_T2 = _i32("kwh_pos_t2", 0x0048, WEIGHT_KWH)
REG_KWH_NEG_TOT = _i32("kwh_neg_tot", 0x004E, WEIGHT_KWH)
REG_KVARH_NEG_TOT = _i32("kvarh_neg_tot", 0x0050, WEIGHT_KVARH)

# Documented as "only ET series and EM330"; zero elsewhere.
REG_RUN_HOUR_METER = _i32(
    "run_hour_meter", 0x005A, WEIGHT_HOURS, series=ET_SERIES_AND_EM330
)

# Documented as "only ET series"; zero elsewhere.
REG_KWH_NEG_L1 = _i32("kwh_neg_l1", 0x0060, WEIGHT_KWH, series=ET_SERIES)
REG_KWH_NEG_L2 = _i32("kwh_neg_l2", 0x0062, WEIGHT_KWH, series=ET_SERIES)
REG_KWH_NEG_L3 = _i32("kwh_neg_l3", 0x0064, WEIGHT_KWH, series=ET_SERIES)

# --- Table 2.7-1: firmware version and revision -----------------------------
REG_VERSION_CODE = Em300Register(
    name="version_code",
    address=0x0302,
    data_type=RegisterDataType.UINT16,
)
REG_REVISION_CODE = Em300Register(
    name="revision_code",
    address=0x0303,
    data_type=RegisterDataType.UINT16,
)

# --- Table 2.8-1: Carlo Gavazzi identification code -------------------------
# Read "limited to a word at a time": this word doubles as the most significant
# word of V L3-L1, and only yields the identification code on its own.
REG_CG_IDENTIFICATION = Em300Register(
    name="cg_identification",
    address=0x000B,
    data_type=RegisterDataType.UINT16,
    standalone=True,
)

# --- Table 2.9-9: serial number ---------------------------------------------
# Seven consecutive words, each carrying one ASCII character in its LSB.
REG_SERIAL_NUMBER = Em300Register(
    name="serial_number",
    address=0x5000,
    length=7,
    data_type=RegisterDataType.STRING,
)

# --- Table 2.8-2: identification code -> meter series -----------------------
CG_IDENTIFICATION_CODES: dict[int, Series] = {
    331: Series.EM330,
    332: Series.EM330,
    335: Series.ET330,
    336: Series.ET330,
    340: Series.EM340,  # pre-production sample, MSW-LSW word order
    341: Series.EM340,
    345: Series.ET340,
    346: Series.EM341,
    355: Series.EM331,
}

#: Identification code of the engineering sample that reverses the documented
#: word order. Word order detection is not implemented; flagged so the device
#: layer can warn rather than report silently wrong 32-bit values.
CG_CODE_REVERSED_WORD_ORDER = 340


def series_for_identification_code(code: int | None) -> Series | None:
    """Map a Carlo Gavazzi identification code to its meter series.

    Returns ``None`` for an unknown or missing code, which callers treat as
    "assume every register is supported".
    """
    if code is None:
        return None
    return CG_IDENTIFICATION_CODES.get(code)


#: The registers polled on every coordinator update.
EM300_REGISTERS: tuple[Em300Register, ...] = (
    REG_V_L1_N,
    REG_V_L2_N,
    REG_V_L3_N,
    REG_V_L1_L2,
    REG_V_L2_L3,
    REG_V_L3_L1,
    REG_A_L1,
    REG_A_L2,
    REG_A_L3,
    REG_W_L1,
    REG_W_L2,
    REG_W_L3,
    REG_VA_L1,
    REG_VA_L2,
    REG_VA_L3,
    REG_VAR_L1,
    REG_VAR_L2,
    REG_VAR_L3,
    REG_V_LN_SYS,
    REG_V_LL_SYS,
    REG_W_SYS,
    REG_VA_SYS,
    REG_VAR_SYS,
    REG_PF_L1,
    REG_PF_L2,
    REG_PF_L3,
    REG_PF_SYS,
    REG_PHASE_SEQUENCE,
    REG_HZ,
    REG_KWH_POS_TOT,
    REG_KVARH_POS_TOT,
    REG_W_DMD,
    REG_W_DMD_PEAK,
    REG_KWH_POS_PARTIAL,
    REG_KVARH_POS_PARTIAL,
    REG_KWH_POS_L1,
    REG_KWH_POS_L2,
    REG_KWH_POS_L3,
    REG_KWH_POS_T1,
    REG_KWH_POS_T2,
    REG_KWH_NEG_TOT,
    REG_KVARH_NEG_TOT,
    REG_RUN_HOUR_METER,
    REG_KWH_NEG_L1,
    REG_KWH_NEG_L2,
    REG_KWH_NEG_L3,
)

#: Registers read once at setup to identify the meter, not polled.
EM300_IDENTITY_REGISTERS: tuple[Em300Register, ...] = (
    REG_VERSION_CODE,
    REG_REVISION_CODE,
)
