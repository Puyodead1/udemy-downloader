import base64
import codecs
import logging
import os
import subprocess
from typing import IO

import demoji
import requests
from tqdm import tqdm

from udemy_downloader import mp4parse, widevine_pssh_data_pb2

logger = logging.getLogger(__name__)


def extract_kid(mp4_file):
    """
    Parameters
    ----------
    mp4_file : str
        MP4 file with a PSSH header


    Returns
    -------
    String

    """

    boxes = mp4parse.F4VParser.parse(filename=mp4_file)
    if not os.path.exists(mp4_file):
        raise Exception("File does not exist")
    for box in boxes:
        if box.header.box_type == "moov":
            pssh_box = next(x for x in box.pssh if x.system_id == "edef8ba979d64acea3c827dcd51d21ed")
            hex = codecs.decode(pssh_box.payload, "hex")

            pssh = widevine_pssh_data_pb2.WidevinePsshData()
            pssh.ParseFromString(hex)
            content_id = base64.b16encode(pssh.content_id)
            return content_id.decode("utf-8").lower()

    # No Moof or PSSH header found
    return None


def deEmojify(inputStr: str):
    return demoji.replace(inputStr, "")


# from https://stackoverflow.com/a/21978778/9785713
def log_subprocess_output(prefix: str, pipe: IO[bytes]):
    if pipe:
        for line in iter(lambda: pipe.read(1), ""):
            logger.debug("[%s]: %r", prefix, line.decode("utf8").strip())
        pipe.flush()


def durationtoseconds(period):
    """
    @author Jayapraveen
    """

    # Duration format in PTxDxHxMxS
    if period[:2] == "PT":
        period = period[2:]
        day = int(period.split("D")[0] if "D" in period else 0)
        hour = int(period.split("H")[0].split("D")[-1] if "H" in period else 0)
        minute = int(period.split("M")[0].split("H")[-1] if "M" in period else 0)
        second = period.split("S")[0].split("M")[-1]
        # logger.debug("Total time: " + str(day) + " days " + str(hour) + " hours " +
        #       str(minute) + " minutes and " + str(second) + " seconds")
        total_time = float(
            str((day * 24 * 60 * 60) + (hour * 60 * 60) + (minute * 60) + (int(second.split(".")[0])))
            + "."
            + str(int(second.split(".")[-1]))
        )
        return total_time

    else:
        logger.error("Duration Format Error")
        return None


def check_for_aria():
    try:
        subprocess.Popen(["aria2c", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
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
        subprocess.Popen(["ffmpeg"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception(
            "> Unexpected exception while checking for FFMPEG, please tell the program author about this! "
        )
        return True


def check_for_ffmpeg():
    try:
        # Run ffmpeg and capture its output
        result = subprocess.run(["ffmpeg", "-version"], stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        # Parse the first line of the output to extract the version
        first_line = result.stdout.splitlines()[0] if result.stdout else result.stderr.splitlines()[0]
        if "ffmpeg version" in first_line:
            return True, first_line
        else:
            logger.warning("FFmpeg is installed but version information could not be extracted.")
            return True, None
    except FileNotFoundError:
        return False, None
    except Exception:
        logger.exception(
            "> Unexpected exception while checking for FFmpeg, please tell the program author about this! "
        )
        return False, None


def download(url, path, filename):
    """
    @author Puyodead1
    """
    file_size = int(requests.head(url).headers["Content-Length"])
    if os.path.exists(path):
        first_byte = os.path.getsize(path)
    else:
        first_byte = 0
    if first_byte >= file_size:
        return file_size
    header = {"Range": "bytes=%s-%s" % (first_byte, file_size)}
    pbar = tqdm(total=file_size, initial=first_byte, unit="B", unit_scale=True, desc=filename)
    res = requests.get(url, headers=header, stream=True)
    res.raise_for_status()
    with open(path, encoding="utf8", mode="ab") as f:
        for chunk in res.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
                pbar.update(1024)
    pbar.close()
    return file_size


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
    """
    chapters = set()
    for part in chapter_str.split(","):
        if "-" in part:
            try:
                start, end = part.split("-")
                start = int(start.strip())
                end = int(end.strip())
                chapters.update(range(start, end + 1))
            except ValueError:
                logger.error("Invalid range in --chapter argument: %s", part)
        else:
            try:
                chapters.add(int(part.strip()))
            except ValueError:
                logger.error("Invalid chapter number in --chapter argument: %s", part)
    return chapters
