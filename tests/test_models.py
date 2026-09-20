"""Tests for the register data model."""

import pytest
from em300_api.models import (
    ALL_SERIES,
    ET_SERIES,
    Em300Register,
    RegisterDataType,
    Series,
)


@pytest.mark.parametrize(
    ("data_type", "expected"),
    [
        (RegisterDataType.INT16, 1),
        (RegisterDataType.UINT16, 1),
        (RegisterDataType.INT32, 2),
        (RegisterDataType.UINT32, 2),
        (RegisterDataType.INT64, 4),
    ],
)
def test_length_is_derived_from_the_data_type(data_type, expected):
    register = Em300Register(name="x", address=0, data_type=data_type)
    assert register.length == expected


def test_explicit_length_matching_the_data_type_is_accepted():
    register = Em300Register(
        name="x", address=0, data_type=RegisterDataType.INT32, length=2
    )
    assert register.length == 2


def test_wrong_length_for_a_fixed_width_type_is_rejected():
    # The original register map declared a 32-bit value as four words wide,
    # which silently shifted every address after it.
    with pytest.raises(ValueError, match="occupies 2 word"):
        Em300Register(name="x", address=0, data_type=RegisterDataType.INT32, length=4)


def test_string_requires_an_explicit_length():
    with pytest.raises(ValueError, match="requires an explicit length"):
        Em300Register(name="x", address=0, data_type=RegisterDataType.STRING)


def test_string_length_must_be_positive():
    with pytest.raises(ValueError, match="requires an explicit length"):
        Em300Register(name="x", address=0, data_type=RegisterDataType.STRING, length=0)


def test_addresses_span_every_word_of_the_register():
    register = Em300Register(name="x", address=0x0034, data_type=RegisterDataType.INT32)
    assert list(register.addresses) == [0x0034, 0x0035]


def test_addresses_of_a_string_span_its_declared_length():
    register = Em300Register(
        name="x", address=0x5000, data_type=RegisterDataType.STRING, length=7
    )
    assert list(register.addresses) == list(range(0x5000, 0x5007))


def test_registers_are_hashable_and_comparable():
    a = Em300Register(name="x", address=0, data_type=RegisterDataType.INT32)
    b = Em300Register(name="x", address=0, data_type=RegisterDataType.INT32)
    assert a == b
    assert len({a, b}) == 1


class TestSupportedBy:
    """Series filtering decides which entities a given meter gets."""

    def test_unrestricted_register_is_supported_everywhere(self):
        register = Em300Register(name="x", address=0, data_type=RegisterDataType.INT32)
        assert register.series == ALL_SERIES
        assert all(register.supported_by(series) for series in Series)

    def test_restricted_register_is_supported_only_on_its_series(self):
        register = Em300Register(
            name="x",
            address=0,
            data_type=RegisterDataType.INT32,
            series=ET_SERIES,
        )
        assert register.supported_by(Series.ET340)
        assert not register.supported_by(Series.EM340)

    def test_unknown_series_is_treated_as_supporting_everything(self):
        # A meter whose identification code could not be read should still get
        # the full entity set rather than none of it.
        register = Em300Register(
            name="x",
            address=0,
            data_type=RegisterDataType.INT32,
            series=ET_SERIES,
        )
        assert register.supported_by(None)
