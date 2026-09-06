"""Builds minimal synthetic .psd files for testing psd_utils.read_psd
without needing real Photoshop assets."""
from __future__ import annotations

import struct
from pathlib import Path


def build_minimal_psd(
    width: int,
    height: int,
    ppi: float = 300.0,
    channels: int = 3,
    bit_depth: int = 8,
    color_mode: int = 3,
    layer_count: int = 2,
) -> bytes:
    out = bytearray()
    out += b"8BPS"
    out += struct.pack(">H", 1)  # version
    out += b"\x00" * 6  # reserved
    out += struct.pack(">H", channels)
    out += struct.pack(">I", height)
    out += struct.pack(">I", width)
    out += struct.pack(">H", bit_depth)
    out += struct.pack(">H", color_mode)

    # Color mode data section (empty)
    out += struct.pack(">I", 0)

    # Image resources: one ResolutionInfo block (0x03ED)
    ppi_fixed = int(round(ppi * 65536))
    res_data = struct.pack(">IHHIHH", ppi_fixed, 1, 1, ppi_fixed, 1, 1)
    resource_block = b"8BIM" + struct.pack(">H", 0x03ED) + b"\x00\x00" + struct.pack(">I", len(res_data)) + res_data
    if len(res_data) % 2 != 0:
        resource_block += b"\x00"
    out += struct.pack(">I", len(resource_block))
    out += resource_block

    # Layer and mask info section
    layer_info = struct.pack(">h", -layer_count if layer_count else 0)
    # pad layer_info to even length is not required by spec here since we
    # keep it minimal - just the count field, no actual layer records.
    layer_info_section = struct.pack(">I", len(layer_info)) + layer_info
    lm_section = layer_info_section
    out += struct.pack(">I", len(lm_section))
    out += lm_section

    # Image data section (irrelevant for our reader) - leave empty
    return bytes(out)


def write_test_psd(path: str | Path, **kwargs) -> None:
    Path(path).write_bytes(build_minimal_psd(**kwargs))
