#!/usr/bin/env python3
"""Extend the legacy Java observations without revising its historical bytes.

The modern Fourier-filter output is record-length dependent, so recomputing the
whole 1950-present interval changes the values shown by the original applet.
This builder keeps the complete legacy file verbatim, adds four Hermite bridge
samples after its January 2013 endpoint, and then appends the modern series from
February 2013 onward.
"""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = (
    ROOT
    / "legacy-java"
    / "observations-2013"
    / "sva.2_filter_10_9_1950.1_2013.01.dat"
)
DEFAULT_MODERN = (
    ROOT
    / "data"
    / "output"
    / "sva.2_filter_10_9_1975.1_2026.6_SAIDApy.dat"
)
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "java"
    / "observations-2013"
    / "sva.2_filter_10_9_1950.1_2026.06.dat"
)


def parse_row(line: bytes) -> tuple[float, float, int, int, int]:
    fields = [field.strip() for field in line.decode("ascii").split(";")]
    if len(fields) != 5:
        raise ValueError(f"expected five fields, got: {line!r}")
    return float(fields[0]), float(fields[1]), *(int(value) for value in fields[2:])


def format_row(x: float, derivative: float, year: int, month: int, point: int) -> bytes:
    return f"{x:8.2f};{derivative:7.2f}; {year:4d}; {month:2d}; {point:d}\n".encode(
        "ascii"
    )


def hermite_bridge(
    start: tuple[float, float], end: tuple[float, float]
) -> list[tuple[float, float]]:
    """Return the four one-fifth-month samples between two monthly endpoints."""
    x0, slope0 = start
    x1, slope1 = end
    result = []
    for point in range(1, 5):
        t = point / 5
        x = (
            (2 * t**3 - 3 * t**2 + 1) * x0
            + (t**3 - 2 * t**2 + t) * slope0
            + (-2 * t**3 + 3 * t**2) * x1
            + (t**3 - t**2) * slope1
        )
        derivative = (
            (6 * t**2 - 6 * t) * x0
            + (3 * t**2 - 4 * t + 1) * slope0
            + (-6 * t**2 + 6 * t) * x1
            + (3 * t**2 - 2 * t) * slope1
        )
        result.append((x, derivative))
    return result


def build(baseline_path: Path, modern_path: Path, output_path: Path) -> None:
    baseline = baseline_path.read_bytes()
    baseline_lines = baseline.splitlines()
    old_x, old_slope, old_year, old_month, old_point = parse_row(baseline_lines[-1])
    if (old_year, old_month, old_point) != (2013, 1, 0):
        raise ValueError("legacy baseline must end at January 2013, point 0")
    if not baseline.endswith(b"\n"):
        raise ValueError("legacy baseline must end with a newline for byte-safe append")

    modern_lines = modern_path.read_bytes().splitlines()
    modern_rows = [parse_row(line) for line in modern_lines]
    first_new_index = next(
        index
        for index, row in enumerate(modern_rows)
        if (row[2], row[3], row[4]) == (2013, 2, 0)
    )
    first_new = modern_rows[first_new_index]
    if modern_rows[-1][2:] != (2026, 6, 0):
        raise ValueError("modern input must end at June 2026, point 0")

    bridge = b"".join(
        format_row(x, slope, 2013, 1, point)
        for point, (x, slope) in enumerate(
            hermite_bridge((old_x, old_slope), first_new[:2]), start=1
        )
    )
    modern_suffix = b"\n".join(modern_lines[first_new_index:]) + b"\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(baseline + bridge + modern_suffix)

    output = output_path.read_bytes()
    if not output.startswith(baseline):
        raise AssertionError("historical prefix changed while building current data")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--modern", type=Path, default=DEFAULT_MODERN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.baseline, args.modern, args.output)


if __name__ == "__main__":
    main()
