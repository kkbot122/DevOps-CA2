"""Evidence gates must reject corrupt, duplicate and missing required captures."""

import importlib.util
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_screenshots.py"
spec = importlib.util.spec_from_file_location("evidence_check", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def png(width=1000):
    def chunk(kind, body):
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\0" + b"\0\0\0" * width))
        + chunk(b"IEND", b"")
    )


def manifest(tmp_path, names):
    folder = tmp_path / "docs/screenshots"
    folder.mkdir(parents=True)
    (folder / "MANIFEST.md").write_text(
        "\n".join(
            f"| {i} | `{name}` | evidence | url | 1 | MUST |" for i, name in enumerate(names, 1)
        ),
        encoding="utf-8",
    )
    return folder


def test_corrupt_png_is_rejected():
    corrupted = bytearray(png())
    corrupted[30] ^= 1
    with pytest.raises(ValueError, match="checksum"):
        checker.png_width(corrupted)


def test_reusing_one_image_for_two_required_captures_fails(tmp_path):
    folder = manifest(tmp_path, ["a.png", "b.png"])
    for name in ("a.png", "b.png"):
        (folder / name).write_bytes(png())
    assert all(row["status"] == "DUPLICATE" for row in checker.inspect(tmp_path))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--strict"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1


def test_strict_mode_rejects_missing_and_small_required_capture(tmp_path):
    folder = manifest(tmp_path, ["missing.png", "small.png"])
    (folder / "small.png").write_bytes(png(1))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--strict"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "MISSING" in result.stdout and "TOO SMALL" in result.stdout


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("automountServiceAccountToken: false\n", 0),
        ("ADMIN_TOKEN" + ": not-a-demo-credential\n", 1),
    ],
)
def test_credential_scan_distinguishes_config_from_credentials(tmp_path, content, expected):
    (tmp_path / "config.yaml").write_text(content, encoding="utf-8")
    scanner = SCRIPT.parent / "check_submission_secrets.py"
    result = subprocess.run(
        [sys.executable, str(scanner), str(tmp_path)], capture_output=True, text=True
    )
    assert result.returncode == expected
