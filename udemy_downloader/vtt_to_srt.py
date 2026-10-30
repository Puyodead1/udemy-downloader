from webvtt import WebVTT
import html
import os
from pysrt.srtitem import SubRipItem
from pysrt.srttime import SubRipTime


def _to_srt_time(timestamp):
    # start_in_seconds/end_in_seconds truncate to whole seconds, so copy each field to keep milliseconds
    return SubRipTime(timestamp.hours, timestamp.minutes, timestamp.seconds, timestamp.milliseconds)


def convert(directory, filename):
    index = 0
    vtt_filepath = os.path.join(directory, filename + ".vtt")
    srt_filepath = os.path.join(directory, filename + ".srt")
    with open(srt_filepath, mode='w', encoding='utf8', errors='ignore') as srt:
        for caption in WebVTT().read(vtt_filepath):
            index += 1
            start = _to_srt_time(caption.start_time)
            end = _to_srt_time(caption.end_time)
            srt.write(
                SubRipItem(index, start, end, html.unescape(
                    caption.text)).__str__() + "\n")