"""Tests for batched read planning."""

import pytest
from em300_api.batch import MAX_READ_REGISTERS, RegisterBatch, split_addresses
from em300_api.models import Em300Register, RegisterDataType


def i32(name: str, address: int, **kwargs) -> Em300Register:
    return Em300Register(
        name=name, address=address, data_type=RegisterDataType.INT32, **kwargs
    )


class TestSplitAddresses:
    def test_no_addresses_means_no_reads(self):
        assert split_addresses([]) == []

    def test_a_single_address_is_one_word(self):
        assert split_addresses([5]) == [(5, 1)]

    def test_contiguous_addresses_collapse_into_one_read(self):
        assert split_addresses([0, 1, 2, 3]) == [(0, 4)]

    def test_addresses_are_sorted_before_grouping(self):
        assert split_addresses([3, 0, 2, 1]) == [(0, 4)]

    def test_duplicates_do_not_widen_a_read(self):
        assert split_addresses([0, 0, 1, 1]) == [(0, 2)]

    def test_a_gap_starts_a_new_read(self):
        # Never bridge a gap: the identity registers sit thousands of words
        # above the measurements, and reading across the hole in between draws
        # an illegal-data-address exception.
        assert split_addresses([0, 1, 10, 11]) == [(0, 2), (10, 2)]

    def test_a_one_word_gap_still_splits(self):
        assert split_addresses([0, 1, 3]) == [(0, 2), (3, 1)]

    def test_a_run_is_chopped_at_the_frame_limit(self):
        assert split_addresses(range(50), maximum_length=20) == [
            (0, 20),
            (20, 20),
            (40, 10),
        ]

    def test_a_run_exactly_at_the_limit_is_one_read(self):
        assert split_addresses(range(20), maximum_length=20) == [(0, 20)]

    def test_no_read_ever_exceeds_the_protocol_limit(self):
        reads = split_addresses(range(500))
        assert all(length <= MAX_READ_REGISTERS for _, length in reads)

    def test_the_protocol_limit_matches_the_request_frame(self):
        # Section 1.2.1's prose says 50, but its request frame constrains the
        # quantity field to 1..0x14. The frame is what goes on the wire.
        assert MAX_READ_REGISTERS == 20


class TestRegisterBatch:
    def test_a_32_bit_register_reserves_both_of_its_words(self):
        # Collecting only the start address left the high word unread, so
        # every 32-bit value decoded as missing.
        batch = RegisterBatch([i32("a", 0x0000)])
        assert batch.reads == [(0x0000, 2)]
        assert batch.addresses == {0x0000, 0x0001}

    def test_adjacent_registers_merge_into_one_read(self):
        batch = RegisterBatch([i32("a", 0), i32("b", 2), i32("c", 4)])
        assert batch.reads == [(0, 6)]

    def test_separated_registers_get_their_own_reads(self):
        batch = RegisterBatch([i32("a", 0x0000), i32("b", 0x5000)])
        assert batch.reads == [(0x0000, 2), (0x5000, 2)]

    def test_every_word_of_every_register_is_covered(self):
        registers = [i32(f"r{n}", n * 2) for n in range(30)]
        batch = RegisterBatch(registers)
        for register in registers:
            assert set(register.addresses) <= batch.addresses

    def test_standalone_registers_are_kept_out_of_the_batched_reads(self):
        # The identification code shares a word with V L3-L1 and is only
        # meaningful when read on its own.
        standalone = Em300Register(
            name="id",
            address=0x000B,
            data_type=RegisterDataType.UINT16,
            standalone=True,
        )
        batch = RegisterBatch([i32("v", 0x0000), standalone])

        assert batch.reads == [(0x0000, 2)]
        assert 0x000B not in batch.addresses

    def test_registers_are_kept_for_decoding(self):
        registers = [i32("a", 0), i32("b", 2)]
        assert RegisterBatch(registers).registers == tuple(registers)

    def test_an_empty_batch_plans_nothing(self):
        batch = RegisterBatch([])
        assert batch.reads == []
        assert batch.addresses == set()


@pytest.mark.parametrize("count", [1, 5, 21, 100])
def test_every_planned_read_is_within_the_frame_limit(count):
    registers = [i32(f"r{n}", n * 2) for n in range(count)]
    for _, length in RegisterBatch(registers).reads:
        assert 1 <= length <= MAX_READ_REGISTERS
