"""Batch-read planning for the EM/ET300.

A coordinator poll needs several dozen words that are mostly contiguous. This
module turns the set of words the integration wants into the smallest set of
``(start, length)`` read requests that respects the protocol's per-request cap,
so each poll issues as few Modbus transactions as possible.
"""

from __future__ import annotations

from collections.abc import Iterable

from .models import Em300Register

#: Maximum words in a single read request.
#:
#: Section 1.2.1 of the protocol is self-contradictory here: the prose says
#: "maximum 50 registers (words) with a single request", while the request
#: frame table immediately below it constrains the quantity field to "1 to 14h
#: (1 to 20)". The frame table describes what actually goes on the wire, so the
#: lower of the two is used.
MAX_READ_REGISTERS = 20


def split_addresses(
    addresses: Iterable[int], maximum_length: int = MAX_READ_REGISTERS
) -> list[tuple[int, int]]:
    """Group word addresses into ``(start, length)`` read requests.

    Addresses are sorted and collapsed into contiguous runs; a run longer than
    ``maximum_length`` is chopped into successive requests so none exceeds the
    frame limit. Gaps are never bridged -- the identity registers sit thousands
    of words above the measurements, and reading across the hole in between
    would draw an illegal-data-address exception.
    """
    ordered = sorted(set(addresses))
    if not ordered:
        return []

    reads: list[tuple[int, int]] = []
    run_start = run_end = ordered[0]

    for address in ordered[1:]:
        if address == run_end + 1:
            run_end = address
            continue
        reads.extend(_split_run(run_start, run_end, maximum_length))
        run_start = run_end = address

    reads.extend(_split_run(run_start, run_end, maximum_length))
    return reads


def _split_run(start: int, end: int, maximum_length: int) -> list[tuple[int, int]]:
    """Chop the inclusive run ``[start, end]`` into <= maximum_length chunks."""
    width = end - start + 1
    return [
        (start + offset, min(maximum_length, width - offset))
        for offset in range(0, width, maximum_length)
    ]


class RegisterBatch:
    """The read requests needed to cover a set of registers.

    Registers the protocol requires be read one word at a time are excluded;
    the device layer reads those individually.
    """

    def __init__(self, registers: Iterable[Em300Register]) -> None:
        """Plan the reads covering every word the given registers span."""
        self.registers: tuple[Em300Register, ...] = tuple(registers)

        # A register spans ``length`` words, not one: collecting only the start
        # address would leave the high word of every 32-bit value unread.
        words = {
            address
            for register in self.registers
            if not register.standalone
            for address in register.addresses
        }
        self.reads: list[tuple[int, int]] = split_addresses(words)

    @property
    def addresses(self) -> set[int]:
        """Every word address the batched reads cover."""
        return {
            address
            for start, length in self.reads
            for address in range(start, start + length)
        }
