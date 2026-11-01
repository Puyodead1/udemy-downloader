import json
import logging
import os
import re
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


def _iter_child_boxes(data: bytes, start: int, end: int):
    """Yield (box_type, offset, header_size, box_size) for each box between start and end"""
    offset = start
    while offset < end and (box := _read_box_header(data[:end], offset)) is not None:
        box_type, header_size, box_size = box
        yield box_type, offset, header_size, box_size
        offset += box_size


def _empty_saiz_type_offsets(moof: bytes):
    """Offsets of the type fields of empty saiz boxes (and their saio) in a moof box"""
    offsets = []
    moof_box = _read_box_header(moof, 0)
    if moof_box is None:
        # truncated file
        return offsets
    _, moof_header, moof_size = moof_box
    for box_type, traf_offset, traf_header, traf_size in _iter_child_boxes(moof, moof_header, moof_size):
        if box_type != b"traf":
            continue
        children = list(_iter_child_boxes(moof, traf_offset + traf_header, traf_offset + traf_size))
        for child_type, child_offset, child_header, _ in children:
            if child_type != b"saiz":
                continue
            # saiz layout: header, 1 byte version, 3 byte flags, [aux info type + param], default size, sample count
            body = child_offset + child_header
            flags = int.from_bytes(moof[body + 1 : body + 4], "big")
            pos = body + 4 + (8 if flags & 1 else 0)
            default_size = moof[pos]
            sample_count = struct.unpack_from(">I", moof, pos + 1)[0]
            if default_size == 0 and sample_count == 0:
                offsets += [offset + 4 for box_type, offset, _, _ in children if box_type in (b"saiz", b"saio")]
    return offsets


def fix_empty_saiz(mp4_file):
    """
    Turn empty saiz boxes (default size 0 and sample count 0), and the saio boxes that go with them, into free boxes.

    Udemy writes these for fully encrypted audio that has no per-sample encryption info. FFmpeg rejects a saiz like
    this with "Invalid data found when processing input" before it reaches the senc box that has the same information,
    so without the fix the audio can't be decrypted or muxed. See issues #307 and #314.

    Returns the number of boxes that were changed.
    """
    patches = []
    with open(mp4_file, "r+b") as f:
        file_size = os.fstat(f.fileno()).st_size
        offset = 0
        # walk the top-level boxes without reading media data into memory
        while offset + 8 <= file_size:
            f.seek(offset)
            header = f.read(16)
            box = _read_box_header(header, 0)
            if box is None:
                break
            box_type, _, box_size = box
            if struct.unpack_from(">I", header)[0] == 0:
                # a size of 0 means the box runs to the end of the file
                box_size = file_size - offset
            if box_type == b"moof":
                f.seek(offset)
                patches += [offset + p for p in _empty_saiz_type_offsets(f.read(box_size))]
            offset += box_size

        for patch in patches:
            f.seek(patch)
            f.write(b"free")
    return len(patches)


def _find_role_play(data):
    """Depth-first search for the object that describes the role play"""
    if isinstance(data, dict):
        if "scenario" in data and ("aiCharacter" in data or "learnerRole" in data or "meeting" in data):
            return data
        children = data.values()
    elif isinstance(data, list):
        children = data
    else:
        return None
    for child in children:
        found = _find_role_play(child)
        if found:
            return found
    return None


def _resolve_flight_refs(data, payload: str):
    """Replace "$<id>" references in Next.js flight data with the chunk they point to"""
    if isinstance(data, dict):
        return {key: _resolve_flight_refs(value, payload) for key, value in data.items()}
    if isinstance(data, list):
        return [_resolve_flight_refs(item, payload) for item in data]
    if not (isinstance(data, str) and data.startswith("$") and len(data) > 1):
        return data

    chunk_id = data[1:]
    # text chunks look like "<id>:T<hex byte length>,<text>"
    idx = payload.find(f"{chunk_id}:T")
    if idx != -1:
        comma_idx = payload.find(",", idx)
        if comma_idx != -1:
            try:
                byte_len = int(payload[idx + len(chunk_id) + 2 : comma_idx], 16)
                start_bytes = len(payload[: comma_idx + 1].encode("utf-8"))
                return payload.encode("utf-8")[start_bytes : start_bytes + byte_len].decode("utf-8")
            except ValueError:
                pass
        return data

    # json chunks look like "<id>:<json>" on their own line
    prefix = f'{chunk_id}:"'
    if payload.startswith(prefix):
        idx = 0
    else:
        idx = payload.find(f"\n{prefix}")
        if idx == -1:
            return data
        idx += 1
    end_idx = payload.find("\n", idx)
    if end_idx == -1:
        end_idx = len(payload)
    try:
        return json.loads(payload[idx + len(chunk_id) + 1 : end_idx])
    except ValueError:
        return data


def extract_role_play(page_html: str):
    """Extract the role play data from a role play page's Next.js payload, or None if it isn't there"""
    # the page streams its data as self.__next_f.push([<type>, "<chunk>"]) calls
    payload = ""
    for _, chunk in re.findall(r'__next_f.*?\.push\(\[(\d+),\s*("(?:[^"\\]|\\.)*")\]\)', page_html, re.DOTALL):
        content = json.loads(chunk)
        if isinstance(content, str):
            payload += content
    if not payload:
        payload = page_html

    for line in payload.split("\n"):
        parts = line.split(":", 1)
        if len(parts) != 2:
            continue
        try:
            found = _find_role_play(json.loads(parts[1]))
        except ValueError:
            continue
        if found:
            return _resolve_flight_refs(found, payload)
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
