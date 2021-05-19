from webvtt import WebVTT
import html
from pysrt.srtitem import SubRipItem
from pysrt.srttime import SubRipTime


def convert(directory, filename):
    index = 0
    vtt_filepath = f"%s\\%s.vtt" % (directory, filename)
    srt_filepath = f"%s\\%s.srt" % (directory, filename)
    srt = open(srt_filepath, "w")

    for caption in WebVTT().read(vtt_filepath):
        index += 1
        start = SubRipTime(0, 0, caption.start_in_seconds)
        end = SubRipTime(0, 0, caption.end_in_seconds)
        srt.write(
            SubRipItem(index, start, end, html.unescape(
                caption.text)).__str__() + "\n")
