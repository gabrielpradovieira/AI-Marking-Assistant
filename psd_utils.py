"""Pure-Python PSD header reader.

Reads just enough of the PSD file format (Adobe Photoshop Document) to answer
the questions the marking tool needs: canvas size and resolution (PPI). No
external dependency - the format is documented and stable, and we only need
the fixed header plus the ResolutionInfo image resource block.

Reference: Adobe Photoshop File Formats Specification.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


class PSDParseError(Exception):
    """Raised when a file is not a well-formed PSD/PSB we can read."""


@dataclass
class PSDInfo:
    width: int
    height: int
    channels: int
    bit_depth: int
    color_mode: int
    ppi_horizontal: float | None
    ppi_vertical: float | None
    layer_count: int | None


def _read_pascal_string_padded(f) -> bytes:
    """Read a Pascal string (1-byte length prefix) padded to an even length
    (the length byte itself counts towards the padding total used by PSD
    image resource blocks)."""
    (length,) = struct.unpack(">B", f.read(1))
    data = f.read(length)
    total = 1 + length
    if total % 2 != 0:
        f.read(1)
    return data


def _parse_resolution_info(data: bytes) -> tuple[float, float]:
    # ResolutionInfo (image resource 0x03ED / 1005):
    #   4 bytes  hRes (Fixed 16.16, pixels per inch)
    #   2 bytes  hResUnit
    #   2 bytes  widthUnit
    #   4 bytes  vRes (Fixed 16.16, pixels per inch)
    #   2 bytes  vResUnit
    #   2 bytes  heightUnit
    if len(data) < 16:
        raise PSDParseError("ResolutionInfo block too short")
    h_res_fixed, h_res_unit, width_unit, v_res_fixed, v_res_unit, height_unit = (
        struct.unpack(">IHHIHH", data[:16])
    )
    h_res = h_res_fixed / 65536.0
    v_res = v_res_fixed / 65536.0
    return h_res, v_res


def read_psd(path: str | Path) -> PSDInfo:
    """Parse a .psd/.psb file header and return the fields the marking tool
    needs. Raises PSDParseError on anything that doesn't look like a PSD."""
    path = Path(path)
    with open(path, "rb") as f:
        signature = f.read(4)
        if signature != b"8BPS":
            raise PSDParseError(f"Not a PSD file (bad signature): {path.name}")

        (version,) = struct.unpack(">H", f.read(2))
        if version not in (1, 2):
            raise PSDParseError(f"Unsupported PSD version {version}: {path.name}")

        f.read(6)  # reserved, must be zero

        (channels,) = struct.unpack(">H", f.read(2))
        (height,) = struct.unpack(">I", f.read(4))
        (width,) = struct.unpack(">I", f.read(4))
        (bit_depth,) = struct.unpack(">H", f.read(2))
        (color_mode,) = struct.unpack(">H", f.read(2))

        # --- Color Mode Data section ---
        (cmd_length,) = struct.unpack(">I", f.read(4))
        f.read(cmd_length)

        # --- Image Resources section ---
        (ir_length,) = struct.unpack(">I", f.read(4))
        ir_end = f.tell() + ir_length

        ppi_h = ppi_v = None
        while f.tell() < ir_end:
            block_sig = f.read(4)
            if block_sig != b"8BIM":
                # Malformed / unexpected resource block; stop scanning
                # resources rather than risk mis-parsing the rest of the file.
                break
            (resource_id,) = struct.unpack(">H", f.read(2))
            _read_pascal_string_padded(f)  # name, unused
            (res_size,) = struct.unpack(">I", f.read(4))
            res_data = f.read(res_size)
            if res_size % 2 != 0:
                f.read(1)  # padding byte

            if resource_id == 0x03ED:  # ResolutionInfo
                ppi_h, ppi_v = _parse_resolution_info(res_data)

        f.seek(ir_end)

        # --- Layer and Mask Information section ---
        layer_count = None
        try:
            if version == 1:
                (lm_length,) = struct.unpack(">I", f.read(4))
            else:  # PSB
                (lm_length,) = struct.unpack(">Q", f.read(8))
            lm_end = f.tell() + lm_length
            if lm_length > 0:
                if version == 1:
                    (layer_info_length,) = struct.unpack(">I", f.read(4))
                else:
                    (layer_info_length,) = struct.unpack(">Q", f.read(8))
                if layer_info_length > 0:
                    (raw_count,) = struct.unpack(">h", f.read(2))
                    # A negative count means the first alpha channel is the
                    # merged image's transparency mask; the real layer count
                    # is the absolute value.
                    layer_count = abs(raw_count)
            f.seek(lm_end)
        except struct.error:
            layer_count = None

        return PSDInfo(
            width=width,
            height=height,
            channels=channels,
            bit_depth=bit_depth,
            color_mode=color_mode,
            ppi_horizontal=ppi_h,
            ppi_vertical=ppi_v,
            layer_count=layer_count,
        )
