"""Fake device, path, and file fixtures for tests — not real hardware or user data."""

from __future__ import annotations

from datetime import date, datetime

MOCK_INFO_VERSION = "9.9"
MOCK_CAMERA_TYPE = "MOCK CAM XL"
MOCK_CAMERA_TYPE_ALT = "MOCKHERO"
MOCK_FIRMWARE = "X99.00.00.00.00"
MOCK_MCU = "MOCK-MCU-9.9.9"
MOCK_SERIAL = "MOCK-SERIAL-00000001"
MOCK_SERIAL_ALT = "MOCK-SERIAL-00000002"
MOCK_WIFI_MAC = "00:MO:CK:00:00:01"

MOCK_CLIP_BASENAME = "MOCK0001"
MOCK_CLIP_FILENAME = f"{MOCK_CLIP_BASENAME}.MP4"
MOCK_CLIP_RENAME = f"{MOCK_CLIP_BASENAME}_1.MP4"

MOCK_ARCHIVE_DATE = date(2030, 4, 1)
MOCK_ARCHIVE_DATETIME = datetime(2030, 4, 1, 12, 0, 0)
MOCK_ARCHIVE_YEAR = str(MOCK_ARCHIVE_DATE.year)
MOCK_ARCHIVE_DAY = MOCK_ARCHIVE_DATE.isoformat()

MOCK_FAVORITE_PATH_A = "/mock/archive/alpha"
MOCK_FAVORITE_PATH_B = "/mock/archive/beta"

MOCK_CARD_LABEL = "MOCKCARD"
MOCK_LINUX_USER = "mockuser"


def mock_version_metadata(
    *,
    camera_type: str = MOCK_CAMERA_TYPE,
    serial: str = MOCK_SERIAL,
    firmware: str = MOCK_FIRMWARE,
    mcu: str = MOCK_MCU,
    wifi_mac: str = MOCK_WIFI_MAC,
) -> dict[str, str]:
    return {
        "info version": MOCK_INFO_VERSION,
        "camera type": camera_type,
        "camera serial number": serial,
        "firmware version": firmware,
        "mcu version": mcu,
        "wifi mac": wifi_mac,
    }
