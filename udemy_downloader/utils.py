import logging
import os
import struct
import subprocess
from typing import IO

import demoji
from pywidevine.pssh import PSSH

logger = logging.getLogger(__name__)

WIDEVINE_SYSTEM_ID = bytes.fromhex("edef8ba979d64acea3c827dcd51d21ed")


def _read_box_header(data: bytes, offset: int):
    """Return (box_type, header_size, box_size) for the mp4 box at offset, or None if truncated."""
    if offset + 8 > len(data):
        return None
    size, box_type = struct.unpack_from(">I4s", data, offset)
    header_size = 8
    if size == 1:
        if offset + 16 > len(data):
            return None
        size = struct.unpack_from(">Q", data, offset + 8)[0]
        header_size = 16
    elif size == 0:
        size = len(data) - offset
    if size < header_size:
        return None
    return box_type, header_size, size


def extract_pssh(mp4_file):
    """
    Parameters
    ----------
    mp4_file : str
        MP4 file with a PSSH header


    Returns
    -------
    PSSH, or None if the moov box has no Widevine PSSH box

    """
    if not os.path.exists(mp4_file):
        raise Exception("File does not exist")

    with open(mp4_file, "rb") as f:
        # walk the top-level boxes without reading media data into memory
        while True:
            header = f.read(16)
            box = _read_box_header(header, 0)
            if box is None:
                return None
            box_type, header_size, box_size = box
            if box_type == b"moov":
                f.seek(header_size - len(header), os.SEEK_CUR)
                moov = f.read(box_size - header_size)
                break
            if struct.unpack_from(">I", header)[0] == 0:
                # a size of 0 means the box runs to the end of the file
                return None
            f.seek(box_size - len(header), os.SEEK_CUR)

    offset = 0
    while (box := _read_box_header(moov, offset)) is not None:
        box_type, header_size, box_size = box
        # pssh layout: header, 4 bytes version/flags, 16 byte system id
        system_id = moov[offset + header_size + 4 : offset + header_size + 20]
        if box_type == b"pssh" and system_id == WIDEVINE_SYSTEM_ID:
            return PSSH(moov[offset : offset + box_size])
        offset += box_size

    # No Widevine PSSH box found
    return None


def deEmojify(inputStr: str):
    return demoji.replace(inputStr, "")


# from https://stackoverflow.com/a/21978778/9785713
def log_subprocess_output(prefix: str, pipe: IO[bytes]):
    if pipe:
        for line in iter(pipe.readline, b""):
            logger.debug("[%s]: %r", prefix, line.decode("utf8").strip())
        pipe.flush()


def check_for_aria():
    try:
        subprocess.Popen(
            ["aria2c", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception(
            "> Unexpected exception while checking for Aria2c, please tell the program author about this! "
        )
        return True


def check_for_ffmpeg():
    try:
        # Run ffmpeg and capture its output
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        # Parse the first line of the output to extract the version
        first_line = (
            result.stdout.splitlines()[0]
            if result.stdout
            else result.stderr.splitlines()[0]
        )
        if "ffmpeg version" in first_line:
            return True, first_line
        else:
            logger.warning(
                "FFmpeg is installed but version information could not be extracted."
            )
            return True, None
    except FileNotFoundError:
        return False, None
    except Exception:
        logger.exception(
            "> Unexpected exception while checking for FFmpeg, please tell the program author about this! "
        )
        return False, None


def download_aria(url, file_dir, filename):
    """
    @author Puyodead1
    """
    args = [
        "aria2c",
        url,
        "-o",
        filename,
        "-d",
        file_dir,
        "-j16",
        "-s20",
        "-x16",
        "-c",
        "--auto-file-renaming=false",
        "--summary-interval=0",
        "--disable-ipv6",
        "--follow-torrent=false",
    ]
    process = subprocess.Popen(args)
    log_subprocess_output("ARIA2-STDOUT", process.stdout)
    log_subprocess_output("ARIA2-STDERR", process.stderr)
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception("Return code from the downloader was non-0 (error)")
    return ret_code


def parse_chapter_filter(chapter_str: str):
    """
    Given a string like "1,3-5,7,9-11", return a set of chapter numbers.

    Raises ValueError describing the first invalid part.
    """
    chapters = set()
    for part in chapter_str.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = (int(x.strip()) for x in part.split("-"))
            except ValueError:
                raise ValueError(f"invalid chapter range '{part}', expected e.g. '3-5'")
            if start > end:
                raise ValueError(f"invalid chapter range '{part}', the start is after the end")
            chapters.update(range(start, end + 1))
        else:
            try:
                chapters.add(int(part))
            except ValueError:
                raise ValueError(f"invalid chapter number '{part}', expected e.g. '1,3-5,7'")
    return chapters
