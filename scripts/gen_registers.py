"""Generate the EM300 register map from the source JSON.

Run from the repo root:
    python scripts/gen_registers.py

Emits ``EM300_REGISTERS`` entries (one JSON object per register) to stdout, one
line each, so the map can be reviewed/hand-tuned. This centralises the address
math: the ``word`` field of the JSON is the exact pymodbus register address, and
``length`` (bytes) / 2 is the register width.
"""

import json
import sys
from dataclasses import dataclass
from enum import Enum

ROOT = "EM330_EM340_ET330_ET340_CP_registers.json"

UNIT_WEIGHT = {
    "Volt": 10,
    "Watt": 10,
    "Ampere": 1000,
    "VA": 10,
    "kvar": 10,
    "kWh": 10,
    "kvarh": 10,
    "PF": 1000,
    "Hz": 10,
    "Run": 100,
}

DT = {"IEEE754": "ieee754", "INT32": "int32", "UINT32": "uint32", "UINT16": "uint16"}


def parse_word(word: str) -> int:
    w = word.lower().strip()
    if w.endswith("h"):
        w = w[:-1]
    return int(w, 16)


@dataclass
class Raw:
    name: str
    address: int
    length: int
    data_type: str
    scale: float | None


def main() -> None:
    doc = json.load(open(ROOT))["document"]
    weight = doc.get("value_weights", {})

    for table in doc["tables"]:
        for reg in table["registers"]:
            variable = (reg.get("variable") or "").strip()
            notes = (reg.get("notes") or "").strip()
            if not variable or variable.upper() in ("N.A.", "N.A", "NOT AVAILABLE", "N.A."):
                continue

            dtype = DT.get((reg.get("data_type") or "").upper())
            if dtype is None:
                print(f"# SKIP unknown dtype {reg.get('data_type')} @ {reg['word']} ({variable})", file=sys.stderr)
                continue

            # Derive scale from the leading unit token of the variable name.
            scale = None
            first = variable.split()[0]
            weight_key = next((k for k in weight if k.lower() in first.lower() or k.lower() == first.lower()), None)
            if weight_key:
                scale = float(weight[weight_key])

            name = slugify(variable)
            print(json.dumps({"name": name, "address": parse_word(reg["word"]), "length": int(reg["length"]) // 2, "data_type": dtype, "scale": scale}))


def slugify(s: str) -> str:
    out = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -:/.":
            out.append("_")
    return "_".join(p for p in "".join(out).split("_") if p)


if __name__ == "__main__":
    main()
