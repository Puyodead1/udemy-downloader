import codecs
import base64
import re
import os
import glob
import subprocess
import sys
from mp4parse import F4VParser
from widevine_pssh_pb2 import WidevinePsshData
from sanitize import sanitize, slugify, SLUG_OK


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

    boxes = F4VParser.parse(filename=mp4_file)
    for box in boxes:
        if box.header.box_type == 'moov':
            pssh_box = next(x for x in box.pssh if x.system_id ==
                            "edef8ba979d64acea3c827dcd51d21ed")
            hex = codecs.decode(pssh_box.payload, "hex")

            pssh = WidevinePsshData()
            pssh.ParseFromString(hex)
            content_id = base64.b16encode(pssh.content_id)
            return content_id.decode("utf-8")

    # No Moof or PSSH header found
    return None


def _clean(text):
    ok = re.compile(r'[^\\/:*?!"<>|]')
    text = "".join(x if ok.match(x) else "_" for x in text)
    text = re.sub(r"\.+$", "", text.strip())
    return text


def _sanitize(self, unsafetext):
    text = _clean(sanitize(
        slugify(unsafetext, lower=False, spaces=True, ok=SLUG_OK + "().[]")))
    return text


def durationtoseconds(period):
    """
    @author Jayapraveen
    """

    # Duration format in PTxDxHxMxS
    if (period[:2] == "PT"):
        period = period[2:]
        day = int(period.split("D")[0] if 'D' in period else 0)
        hour = int(period.split("H")[0].split("D")[-1] if 'H' in period else 0)
        minute = int(
            period.split("M")[0].split("H")[-1] if 'M' in period else 0)
        second = period.split("S")[0].split("M")[-1]
        print("Total time: " + str(day) + " days " + str(hour) + " hours " +
              str(minute) + " minutes and " + str(second) + " seconds")
        total_time = float(
            str((day * 24 * 60 * 60) + (hour * 60 * 60) + (minute * 60) +
                (int(second.split('.')[0]))) + '.' +
            str(int(second.split('.')[-1])))
        return total_time

    else:
        print("Duration Format Error")
        return None


def cleanup(path):
    """
    @author Jayapraveen
    """
    leftover_files = glob.glob(path + '/*.mp4', recursive=True)
    for file_list in leftover_files:
        try:
            os.remove(file_list)
        except OSError:
            print(f"Error deleting file: {file_list}")
    os.removedirs(path)


def remove_files(files):
    for file in files:
        os.remove(file)


def merge(video_title, video_filepath, audio_filepath, output_path, use_h265, h265_crf, ffmpeg_preset, h265_encoder, ffmpeg_framerate):
    """
    @author Jayapraveen
    """
    if os.name == "nt":
        if use_h265:
            command = "ffmpeg -y -i \"{}\" -i \"{}\" -c:v {} -filter:v fps={} -crf {} -preset {} -c:a copy -fflags +bitexact -map_metadata -1 -metadata title=\"{}\" \"{}\"".format(
                video_filepath, audio_filepath, h265_encoder, ffmpeg_framerate, h265_crf, ffmpeg_preset, video_title, output_path)
        else:
            command = "ffmpeg -y -i \"{}\" -i \"{}\" -c:v copy -filter:v fps={} -preset {} -c:a copy -fflags +bitexact -map_metadata -1 -metadata title=\"{}\" \"{}\"".format(
                video_filepath, audio_filepath, ffmpeg_framerate, ffmpeg_preset, video_title, output_path)
    else:
        if use_h265:
            command = "nide -n 7 ffmpeg -y -i \"{}\" -i \"{}\" -c:v {} -filter:v fps={} -crf {} -preset {} -c:a copy -fflags +bitexact -map_metadata -1 -metadata title=\"{}\" \"{}\"".format(
                video_filepath, audio_filepath, h265_encoder, ffmpeg_framerate, h265_crf, ffmpeg_preset, video_title, output_path)
        else:
            command = "nide -n 7 ffmpeg -y -i \"{}\" -i \"{}\" -c:v copy -filter:v fps={} -preset {} -c:a copy -fflags +bitexact -map_metadata -1 -metadata title=\"{}\" \"{}\"".format(
                video_filepath, audio_filepath, ffmpeg_framerate, ffmpeg_preset, video_title, output_path)
    return os.system(command)


def decrypt(key, in_filepath, out_filepath):
    """
    @author Jayapraveen
    """
    if (os.name == "nt"):
        ret_code = os.system(f"mp4decrypt --key 1:%s \"%s\" \"%s\"" %
                             (key, in_filepath, out_filepath))
    else:
        ret_code = os.system(f"nice -n 7 mp4decrypt --key 1:%s \"%s\" \"%s\"" %
                             (key, in_filepath, out_filepath))

    return ret_code


def check_for_aria():
    try:
        subprocess.Popen(["aria2c", "-v"],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception as e:
        print(
            "> Unexpected exception while checking for Aria2c, please tell the program author about this! ",
            e)
        return True


def check_for_ffmpeg():
    try:
        subprocess.Popen(["ffmpeg"],
                         stderr=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception as e:
        print(
            "> Unexpected exception while checking for FFMPEG, please tell the program author about this! ",
            e)
        return True


def check_for_mp4decrypt():
    try:
        subprocess.Popen(["mp4decrypt"],
                         stderr=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception as e:
        print(
            "> Unexpected exception while checking for MP4Decrypt, please tell the program author about this! ",
            e)
        return True
