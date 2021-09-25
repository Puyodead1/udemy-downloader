"""
MIT License

Copyright (c) 2021 Puyodead1

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import requests
import yt_dlp
from dotenv import load_dotenv
from requests.exceptions import ConnectionError as conn_error
from tqdm import tqdm
from html.parser import HTMLParser as compat_HTMLParser
from sanitize import sanitize, slugify, SLUG_OK
from utils import extract_kid, decrypt, merge, remove_files, _clean, check_for_aria, check_for_ffmpeg, check_for_mp4decrypt
from vtt_to_srt import convert
from Udemy import Udemy
from version import __version__

home_dir = os.getcwd()
download_dir = os.path.join(os.getcwd(), "out_dir")
saved_dir = os.path.join(os.getcwd(), "saved")
keyfile_path = os.path.join(os.getcwd(), "keyfile.json")
course_info_path = os.path.join(saved_dir, "course_info.json")
course_content_path = os.path.join(saved_dir, "course_content.json")
_udemy_path = os.path.join(saved_dir, "_udemy.json")

udemy = None
parser = None
retry = 3
_udemy = {}
course_url = None
downloader = None
dl_assets = False
skip_lectures = False
dl_captions = False
caption_locale = "en"
course = None
resource = None
quality = None
bearer_token = None
course_info = None
course_content = None
portal_name = None
keys = None
course_id = None
course_title = None
title = None
course_name = None
keep_vtt = False
skip_hls = False
print_info = False
load_from_file = False
save_to_file = False
concurrent_connections = 10
access_token = None
use_h265 = False
h265_crf = 28
h265_preset = "medium"

def download_segments(url, format_id, video_title, output_path, lecture_file_name, chapter_dir):
    os.chdir(os.path.join(chapter_dir))
    file_name = lecture_file_name.replace("%", "").replace(".mp4", "")
    video_filepath_enc = file_name + ".encrypted.mp4"
    audio_filepath_enc = file_name + ".encrypted.m4a"
    video_filepath_dec = file_name + ".decrypted.mp4"
    audio_filepath_dec = file_name + ".decrypted.m4a"
    print("> Downloading Lecture Tracks...")
    ret_code = subprocess.Popen([
        "yt-dlp", "--force-generic-extractor", "--allow-unplayable-formats",
        "--concurrent-fragments", f"{concurrent_connections}", "--downloader",
        "aria2c", "--fixup", "never", "-k", "-o", f"{file_name}.encrypted.%(ext)s",
        "-f", format_id, f"{url}"
    ]).wait()
    print("> Lecture Tracks Downloaded")

    print("Return code: " + str(ret_code))
    if ret_code != 0:
        print("Return code from the downloader was non-0 (error), skipping!")
        return


    # tries to decrypt audio and video, and then merge them
    try:
        # tries to decrypt audio
        try:
            audio_kid = extract_kid(audio_filepath_enc)
            print("KID for audio file is: " + audio_kid)
            audio_key = keys[audio_kid.lower()]

            print("> Decrypting audio...")
            ret_code = decrypt(audio_key, audio_filepath_enc, audio_filepath_dec)
            if(ret_code != 0):
                print("WARN: Decrypting returned a non-0 result code which usually indicated an error!")
            else:
                print("Decryption complete")
        except KeyError:
            print("Audio key not found!")
            raise RuntimeError("No audio key")

        # tries to decrypt video
        try:
            video_kid = extract_kid(video_filepath_enc)
            print("KID for video file is: " + video_kid)
            video_key = keys[video_kid.lower()]

            print("> Decrypting video...")
            ret_code2 = decrypt(video_key, video_filepath_enc, video_filepath_dec)
            if(ret_code2 != 0):
                print("WARN: Decrypting returned a non-0 result code which usually indicated an error!")
            else:
                print("Decryption complete")
        except KeyError:
            print("Video key not found!")
            raise RuntimeError("No video key")


        # tries to merge audio and video
        # this should run only if both audio and video decryption returned 0 codes
        print("> Merging audio and video files...")
        ret_code3 = merge(video_title=video_title, video_filepath=video_filepath_dec, audio_filepath=audio_filepath_dec, output_path=output_path, use_h265=use_h265, h265_crf=h265_crf, h265_preset=h265_preset)
        if(ret_code3 != 0):
            print("WARN: Merging returned a non-0 result code which usually indicated an error!")


        if(ret_code == 0 and ret_code2 == 0 and ret_code3 == 0):
            print("> Cleaning up...")
            # remove all the temporary files left over after decryption and merging if there were no errors
            remove_files((video_filepath_enc, video_filepath_dec, audio_filepath_enc, audio_filepath_dec))
            print("> Cleanup complete")
    except Exception as e:
        print(e)
        
    os.chdir(home_dir)


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
    pbar = tqdm(total=file_size,
                initial=first_byte,
                unit='B',
                unit_scale=True,
                desc=filename)
    res = requests.get(url, headers=header, stream=True)
    res.raise_for_status()
    with (open(path, 'ab')) as f:
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
    print("    > Downloading File...")
    ret_code = subprocess.Popen([
        "aria2c", url, "-o", filename, "-d", file_dir, "-j16", "-s20", "-x16",
        "-c", "--auto-file-renaming=false", "--summary-interval=0"
    ]).wait()
    print("    > File Downloaded")

    print("Return code: " + str(ret_code))


def process_caption(caption, lecture_title, lecture_dir, keep_vtt, tries=0):
    filename = f"%s_%s.%s" % (sanitize(lecture_title), caption.get("language"),
                              caption.get("extension"))
    filename_no_ext = f"%s_%s" % (sanitize(lecture_title),
                                  caption.get("language"))
    filepath = os.path.join(lecture_dir, filename)

    if os.path.isfile(filepath):
        print("    > Caption '%s' already downloaded." % filename)
    else:
        print(f"    >  Downloading caption: '%s'" % filename)
        try:
            download_aria(caption.get("download_url"), lecture_dir, filename)
        except Exception as e:
            if tries >= 3:
                print(
                    f"    > Error downloading caption: {e}. Exceeded retries, skipping."
                )
                return
            else:
                print(
                    f"    > Error downloading caption: {e}. Will retry {3-tries} more times."
                )
                process_caption(caption, lecture_title, lecture_dir, keep_vtt,
                                tries + 1)
        if caption.get("extension") == "vtt":
            try:
                print("    > Converting caption to SRT format...")
                convert(lecture_dir, filename_no_ext)
                print("    > Caption conversion complete.")
                if not keep_vtt:
                    os.remove(filepath)
            except Exception as e:
                print(f"    > Error converting caption: {e}")


def process_lecture(lecture, lecture_path, lecture_file_name, chapter_dir):
    lecture_title = lecture.get("lecture_title")
    is_encrypted = lecture.get("is_encrypted")
    lecture_sources = lecture.get("video_sources")

    if is_encrypted:
        if len(lecture_sources) > 0:
            source = lecture_sources[-1]  # last index is the best quality
            if isinstance(quality, int):
                source = min(
                    lecture_sources,
                    key=lambda x: abs(int(x.get("height")) - quality))
            print(f"      > Lecture '%s' has DRM, attempting to download" %
                  lecture_title)
            download_segments(source.get("download_url"),
                            source.get(
                                "format_id"), lecture_title, lecture_path, lecture_file_name, chapter_dir)
        else:
            print(f"      > Lecture '%s' is missing media links" %
                  lecture_title)
            print(len(lecture_sources))
    else:
        sources = lecture.get("sources")
        sources = sorted(sources,
                         key=lambda x: int(x.get("height")),
                         reverse=True)
        if sources:
            if not os.path.isfile(lecture_path):
                print(
                    "      > Lecture doesn't have DRM, attempting to download..."
                )
                source = sources[0]  # first index is the best quality
                if isinstance(quality, int):
                    source = min(
                        sources,
                        key=lambda x: abs(int(x.get("height")) - quality))
                try:
                    print("      ====== Selected quality: ",
                          source.get("type"), source.get("height"))
                    url = source.get("download_url")
                    source_type = source.get("type")
                    if source_type == "hls":
                        temp_filepath = lecture_path.replace(
                            ".mp4", ".%(ext)s")
                        ret_code = subprocess.Popen([
                            "yt-dlp", "--force-generic-extractor",
                            "--concurrent-fragments",
                            f"{concurrent_connections}", "--downloader",
                            "aria2c", "-o", f"{temp_filepath}", f"{url}"
                        ]).wait()
                        if ret_code == 0:
                            # os.rename(temp_filepath, lecture_path)
                            print("      > HLS Download success")
                    else:
                        download_aria(url, chapter_dir, lecture_title + ".mp4")
                except EnvironmentError as e:
                    print(f"      > Error downloading lecture: ", e)
            else:
                print(
                    "      > Lecture '%s' is already downloaded, skipping..." %
                    lecture_title)
        else:
            print("      > Missing sources for lecture", lecture)


def parse():
    total_chapters = _udemy.get("total_chapters")
    total_lectures = _udemy.get("total_lectures")
    print(f"Chapter(s) ({total_chapters})")
    print(f"Lecture(s) ({total_lectures})")

    course_name = _udemy.get("course_title")
    course_dir = os.path.join(download_dir, course_name)
    if not os.path.exists(course_dir):
        os.mkdir(course_dir)

    for chapter in _udemy.get("chapters"):
        chapter_title = chapter.get("chapter_title")
        chapter_index = chapter.get("chapter_index")
        chapter_dir = os.path.join(course_dir, chapter_title)
        if not os.path.exists(chapter_dir):
            os.mkdir(chapter_dir)
        print(
            f"======= Processing chapter {chapter_index} of {total_chapters} ======="
        )

        for lecture in chapter.get("lectures"):
            lecture_title = lecture.get("lecture_title")
            lecture_index = lecture.get("lecture_index")
            lecture_extension = lecture.get("extension")
            extension = "mp4"  # video lectures dont have an extension property, so we assume its mp4
            if lecture_extension != None:
                # if the lecture extension property isnt none, set the extension to the lecture extension
                extension = lecture_extension
            lecture_file_name = sanitize(lecture_title + "." + extension)
            lecture_path = os.path.join(
                chapter_dir,
                lecture_file_name)

            print(
                f"  > Processing lecture {lecture_index} of {total_lectures}")
            if not skip_lectures:
                print(lecture_file_name)
                # Check if the lecture is already downloaded
                if os.path.isfile(lecture_path):
                    print(
                        "      > Lecture '%s' is already downloaded, skipping..." %
                        lecture_title)
                    continue
                else:
                    # Check if the file is an html file
                    if extension == "html":
                        html_content = lecture.get("html_content").encode(
                            "ascii", "ignore").decode("utf8")
                        lecture_path = os.path.join(
                            chapter_dir, "{}.html".format(sanitize(lecture_title)))
                        try:
                            with open(lecture_path, 'w') as f:
                                f.write(html_content)
                                f.close()
                        except Exception as e:
                            print("    > Failed to write html file: ", e)
                            continue
                    else:
                        process_lecture(lecture, lecture_path, lecture_file_name, chapter_dir)

            if dl_assets:
                assets = lecture.get("assets")
                print("    > Processing {} asset(s) for lecture...".format(
                    len(assets)))

                for asset in assets:
                    asset_type = asset.get("type")
                    filename = asset.get("filename")
                    download_url = asset.get("download_url")
                    asset_id = asset.get("id")

                    if asset_type == "article":
                        print(
                            "If you're seeing this message, that means that you reached a secret area that I haven't finished! jk I haven't implemented handling for this asset type, please report this at https://github.com/Puyodead1/udemy-downloader/issues so I can add it. When reporting, please provide the following information: "
                        )
                        print("AssetType: Article; AssetData: ", asset)
                        # html_content = lecture.get("html_content")
                        # lecture_path = os.path.join(
                        #     chapter_dir, "{}.html".format(sanitize(lecture_title)))
                        # try:
                        #     with open(lecture_path, 'w') as f:
                        #         f.write(html_content)
                        #         f.close()
                        # except Exception as e:
                        #     print("Failed to write html file: ", e)
                        #     continue
                    elif asset_type == "video":
                        print(
                            "If you're seeing this message, that means that you reached a secret area that I haven't finished! jk I haven't implemented handling for this asset type, please report this at https://github.com/Puyodead1/udemy-downloader/issues so I can add it. When reporting, please provide the following information: "
                        )
                        print("AssetType: Video; AssetData: ", asset)
                    elif asset_type == "audio" or asset_type == "e-book" or asset_type == "file" or asset_type == "presentation":
                        try:
                            download_aria(download_url, chapter_dir,
                                          f"{asset_id}-{filename}")
                        except Exception as e:
                            print("> Error downloading asset: ", e)
                            continue
                    elif asset_type == "external_link":
                        filepath = os.path.join(chapter_dir, filename)
                        savedirs, name = os.path.split(filepath)
                        filename = u"external-assets-links.txt"
                        filename = os.path.join(savedirs, filename)
                        file_data = []
                        if os.path.isfile(filename):
                            file_data = [
                                i.strip().lower()
                                for i in open(filename,
                                              encoding="utf-8",
                                              errors="ignore") if i
                            ]

                        content = u"\n{}\n{}\n".format(name, download_url)
                        if name.lower() not in file_data:
                            with open(filename,
                                      'a',
                                      encoding="utf-8",
                                      errors="ignore") as f:
                                f.write(content)
                                f.close()

            subtitles = lecture.get("subtitles")
            if dl_captions and subtitles:
                print("Processing {} caption(s)...".format(len(subtitles)))
                for subtitle in subtitles:
                    lang = subtitle.get("language")
                    if lang == caption_locale or caption_locale == "all":
                        process_caption(subtitle, lecture_title, chapter_dir)


def process_course():
    global _udemy
    lecture_counter = 0
    counter = -1
    for entry in course:
        clazz = entry.get("_class")
        asset = entry.get("asset")
        supp_assets = entry.get("supplementary_assets")

        if clazz == "chapter":
            lecture_counter = 0
            lectures = []
            chapter_index = entry.get("object_index")
            chapter_title = "{0:02d} - ".format(chapter_index) + _clean(
                entry.get("title"))

            if chapter_title not in _udemy["chapters"]:
                _udemy["chapters"].append({
                    "chapter_title": chapter_title,
                    "chapter_id": entry.get("id"),
                    "chapter_index": chapter_index,
                    "lectures": []
                })
                counter += 1
        elif clazz == "lecture":
            lecture_counter += 1
            lecture_id = entry.get("id")
            if len(_udemy["chapters"]) == 0:
                lectures = []
                chapter_index = entry.get("object_index")
                chapter_title = "{0:02d} - ".format(
                    chapter_index) + _clean(entry.get("title"))
                if chapter_title not in _udemy["chapters"]:
                    _udemy["chapters"].append({
                        "chapter_title": chapter_title,
                        "chapter_id": lecture_id,
                        "chapter_index": chapter_index,
                        "lectures": []
                    })
                    counter += 1

            if lecture_id:
                print(
                    f"Processing {course.index(entry)} of {len(course)}"
                )
                retVal = []

                if isinstance(asset, dict):
                    asset_type = (asset.get("asset_type").lower()
                                    or asset.get("assetType").lower)
                    if asset_type == "article":
                        if isinstance(supp_assets,
                                        list) and len(supp_assets) > 0:
                            retVal = udemy._extract_supplementary_assets(
                                supp_assets)
                    elif asset_type == "video":
                        if isinstance(supp_assets,
                                        list) and len(supp_assets) > 0:
                            retVal = udemy._extract_supplementary_assets(
                                supp_assets)
                    elif asset_type == "e-book":
                        retVal = udemy._extract_ebook(asset)
                    elif asset_type == "file":
                        retVal = udemy._extract_file(asset)
                    elif asset_type == "presentation":
                        retVal = udemy._extract_ppt(asset)
                    elif asset_type == "audio":
                        retVal = udemy._extract_audio(asset)

                lecture_index = entry.get("object_index")
                lecture_title = "{0:03d} ".format(
                    lecture_counter) + _clean(entry.get("title"))

                if asset.get("stream_urls") != None:
                    # not encrypted
                    data = asset.get("stream_urls")
                    if data and isinstance(data, dict):
                        sources = data.get("Video")
                        tracks = asset.get("captions")
                        #duration = asset.get("time_estimation")
                        sources = udemy._extract_sources(
                            sources, skip_hls)
                        subtitles = udemy._extract_subtitles(tracks)
                        sources_count = len(sources)
                        subtitle_count = len(subtitles)
                        lectures.append({
                            "index": lecture_counter,
                            "lecture_index": lecture_index,
                            "lecture_id": lecture_id,
                            "lecture_title": lecture_title,
                            # "duration": duration,
                            "assets": retVal,
                            "assets_count": len(retVal),
                            "sources": sources,
                            "subtitles": subtitles,
                            "subtitle_count": subtitle_count,
                            "sources_count": sources_count,
                            "is_encrypted": False,
                            "asset_id": asset.get("id")
                        })
                    else:
                        lectures.append({
                            "index":
                            lecture_counter,
                            "lecture_index":
                            lecture_index,
                            "lectures_id":
                            lecture_id,
                            "lecture_title":
                            lecture_title,
                            "html_content":
                            asset.get("body"),
                            "extension":
                            "html",
                            "assets":
                            retVal,
                            "assets_count":
                            len(retVal),
                            "subtitle_count":
                            0,
                            "sources_count":
                            0,
                            "is_encrypted":
                            False,
                            "asset_id":
                            asset.get("id")
                        })
                else:
                    # encrypted
                    data = asset.get("media_sources")
                    if data and isinstance(data, list):
                        sources = udemy._extract_media_sources(data)
                        tracks = asset.get("captions")
                        # duration = asset.get("time_estimation")
                        subtitles = udemy._extract_subtitles(tracks)
                        sources_count = len(sources)
                        subtitle_count = len(subtitles)
                        lectures.append({
                            "index": lecture_counter,
                            "lecture_index": lecture_index,
                            "lectures_id": lecture_id,
                            "lecture_title": lecture_title,
                            # "duration": duration,
                            "assets": retVal,
                            "assets_count": len(retVal),
                            "video_sources": sources,
                            "subtitles": subtitles,
                            "subtitle_count": subtitle_count,
                            "sources_count": sources_count,
                            "is_encrypted": True,
                            "asset_id": asset.get("id")
                        })
                    else:
                        lectures.append({
                            "index":
                            lecture_counter,
                            "lecture_index":
                            lecture_index,
                            "lectures_id":
                            lecture_id,
                            "lecture_title":
                            lecture_title,
                            "html_content":
                            asset.get("body"),
                            "extension":
                            "html",
                            "assets":
                            retVal,
                            "assets_count":
                            len(retVal),
                            "subtitle_count":
                            0,
                            "sources_count":
                            0,
                            "is_encrypted":
                            False,
                            "asset_id":
                            asset.get("id")
                        })
            _udemy["chapters"][counter]["lectures"] = lectures
            _udemy["chapters"][counter]["lecture_count"] = len(
                lectures)
        elif clazz == "quiz":
            lecture_id = entry.get("id")
            if len(_udemy["chapters"]) == 0:
                lectures = []
                chapter_index = entry.get("object_index")
                chapter_title = "{0:02d} - ".format(
                    chapter_index) + _clean(entry.get("title"))
                if chapter_title not in _udemy["chapters"]:
                    lecture_counter = 0
                    _udemy["chapters"].append({
                        "chapter_title": chapter_title,
                        "chapter_id": lecture_id,
                        "chapter_index": chapter_index,
                        "lectures": [],
                    })
                    counter += 1

            _udemy["chapters"][counter]["lectures"] = lectures
            _udemy["chapters"][counter]["lectures_count"] = len(
                lectures)

    _udemy["total_chapters"] = len(_udemy["chapters"])
    _udemy["total_lectures"] = sum([
        entry.get("lecture_count", 0) for entry in _udemy["chapters"]
        if entry
    ])

def get_course_information():
    global course_info, course_id, title, course_title, portal_name
    if(load_from_file):
        if os.path.exists(course_info_path):
            f = open(course_info_path, 'r')
            course_info = json.loads(f.read())
        else:
            print("course_info.json not found, falling back to fetching")
            course_info = udemy._extract_course_info(course_url)
    else:
        course_info = udemy._extract_course_info(course_url)

    course_id = course_info.get("id")
    title = _clean(course_info.get("title"))
    course_title = course_info.get("published_title")
    portal_name = course_info.get("portal_name")

def get_course_content():
    global course_content
    if load_from_file:
        if os.path.exists(course_content_path):
            f = open(course_content_path, 'r')
            course_content = json.loads(f.read())
        else:
            print("course_content.json not found, falling back to fetching")
            course_content = udemy._extract_course_json(course_url, course_id, portal_name)
    else:
        course_content = udemy._extract_course_json(course_url, course_id, portal_name)

def parse_data():
    global _udemy
    if load_from_file:
        f = open(_udemy_path, 'r')
        _udemy = json.loads(f.read())
    else:
        process_course()

def _print_course_info(course_data):
    print("\n\n\n\n")
    course_title = course_data.get("title")
    chapter_count = course_data.get("total_chapters")
    lecture_count = course_data.get("total_lectures")

    print("> Course: {}".format(course_title))
    print("> Total Chapters: {}".format(chapter_count))
    print("> Total Lectures: {}".format(lecture_count))
    print("\n")

    chapters = course_data.get("chapters")
    for chapter in chapters:
        chapter_title = chapter.get("chapter_title")
        chapter_index = chapter.get("chapter_index")
        chapter_lecture_count = chapter.get("lecture_count")
        chapter_lectures = chapter.get("lectures")

        print("> Chapter: {} ({} of {})".format(chapter_title, chapter_index,
                                                chapter_count))

        for lecture in chapter_lectures:
            lecture_title = lecture.get("lecture_title")
            lecture_index = lecture.get("index")
            lecture_asset_count = lecture.get("assets_count")
            lecture_is_encrypted = lecture.get("is_encrypted")
            lecture_subtitles = lecture.get("subtitles")
            lecture_extension = lecture.get("extension")
            lecture_sources = lecture.get("sources")
            lecture_video_sources = lecture.get("video_sources")

            if lecture_sources:
                lecture_sources = sorted(lecture.get("sources"),
                                         key=lambda x: int(x.get("height")),
                                         reverse=True)
            if lecture_video_sources:
                lecture_video_sources = sorted(
                    lecture.get("video_sources"),
                    key=lambda x: int(x.get("height")),
                    reverse=True)

            if lecture_is_encrypted:
                lecture_qualities = [
                    "{}@{}x{}".format(x.get("type"), x.get("width"),
                                      x.get("height"))
                    for x in lecture_video_sources
                ]
            elif not lecture_is_encrypted and lecture_sources:
                lecture_qualities = [
                    "{}@{}x{}".format(x.get("type"), x.get("height"),
                                      x.get("width")) for x in lecture_sources
                ]

            if lecture_extension:
                continue

            print("  > Lecture: {} ({} of {})".format(lecture_title,
                                                      lecture_index,
                                                      chapter_lecture_count))
            print("    > DRM: {}".format(lecture_is_encrypted))
            print("    > Asset Count: {}".format(lecture_asset_count))
            print("    > Captions: {}".format(
                [x.get("language") for x in lecture_subtitles]))
            print("    > Qualities: {}".format(lecture_qualities))

        if chapter_index != chapter_count:
            print("\n\n")

def setup_parser():
    global parser
    parser = argparse.ArgumentParser(description='Udemy Downloader')
    parser.add_argument("-c",
                        "--course-url",
                        dest="course_url",
                        type=str,
                        help="The URL of the course to download",
                        required=True)
    parser.add_argument(
        "-b",
        "--bearer",
        dest="bearer_token",
        type=str,
        help="The Bearer token to use",
    )
    parser.add_argument(
        "-q",
        "--quality",
        dest="quality",
        type=int,
        help="Download specific video quality. If the requested quality isn't available, the closest quality will be used. If not specified, the best quality will be downloaded for each lecture",
    )
    parser.add_argument(
        "-l",
        "--lang",
        dest="lang",
        type=str,
        help="The language to download for captions, specify 'all' to download all captions (Default is 'en')",
    )
    parser.add_argument(
        "-cd",
        "--concurrent-connections",
        dest="concurrent_connections",
        type=int,
        help="The number of maximum concurrent connections per download for segments (HLS and DASH, must be a number 1-30)",
    )
    parser.add_argument(
        "--skip-lectures",
        dest="skip_lectures",
        action="store_true",
        help="If specified, lectures won't be downloaded",
    )
    parser.add_argument(
        "--download-assets",
        dest="download_assets",
        action="store_true",
        help="If specified, lecture assets will be downloaded",
    )
    parser.add_argument(
        "--download-captions",
        dest="download_captions",
        action="store_true",
        help="If specified, captions will be downloaded",
    )
    parser.add_argument(
        "--keep-vtt",
        dest="keep_vtt",
        action="store_true",
        help="If specified, .vtt files won't be removed",
    )
    parser.add_argument(
        "--skip-hls",
        dest="skip_hls",
        action="store_true",
        help="If specified, hls streams will be skipped (faster fetching) (hls streams usually contain 1080p quality for non-drm lectures)",
    )
    parser.add_argument(
        "--info",
        dest="print_info",
        action="store_true",
        help="If specified, only course information will be printed, nothing will be downloaded",
    )
    parser.add_argument(
        "--use-h265",
        dest="use_h265",
        action="store_true",
        help="If specified, videos will be encoded with the H.265 codec",
    )
    parser.add_argument(
        "--h265-crf",
        dest="h265_crf",
        type=int,
        default=28,
        help="Set a custom CRF value for H.265 encoding. FFMPEG default is 28",
    )
    parser.add_argument(
        "--h265-preset",
        dest="h265_preset",
        type=str,
        default="medium",
        help="Set a custom preset value for H.265 encoding. FFMPEG default is medium",
    )
    parser.add_argument(
        "--save-to-file",
        dest="save_to_file",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--load-from-file",
        dest="load_from_file",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("-v", "--version", action="version",
                        version='You are running version {version}'.format(version=__version__))

 
def process_args(args):
    global course_url, bearer_token, dl_assets, caption_locale, skip_lectures, quality, keep_vtt, skip_hls, print_info, load_from_file, save_to_file, concurrent_connections, use_h265, h265_crf, h265_preset
    
    course_url = args.course_url
    if args.download_assets:
        dl_assets = True
    if args.lang:
        caption_locale = args.lang
    if args.download_captions:
        dl_captions = True
    if args.skip_lectures:
        skip_lectures = True
    if args.quality:
        quality = args.quality
    if args.keep_vtt:
        keep_vtt = args.keep_vtt
    if args.skip_hls:
        skip_hls = args.skip_hls
    if args.print_info:
        print_info = args.print_info
    if args.load_from_file:
        load_from_file = args.load_from_file
    if args.save_to_file:
        save_to_file = args.save_to_file
    if args.concurrent_connections:
        concurrent_connections = args.concurrent_connections
        if concurrent_connections <= 0:
            # if the user gave a number that is less than or equal to 0, set cc to default of 10
            concurrent_connections = 10
        elif concurrent_connections > 30:
            # if the user gave a number thats greater than 30, set cc to the max of 30
            concurrent_connections = 30
    if args.use_h265:
        use_h265 = True
    if args.h265_crf:
        h265_crf = args.h265_crf
    if args.h265_preset:
        h265_preset = args.h265_preset

    if args.load_from_file:
        print(
            "> 'load_from_file' was specified, data will be loaded from json files instead of fetched"
        )
    if args.save_to_file:
        print(
            "> 'save_to_file' was specified, data will be saved to json files")

    if args.bearer_token:
        bearer_token = args.bearer_token
    else:
        bearer_token = os.getenv("UDEMY_BEARER")

def ensure_dependencies_installed():
    aria_ret_val = check_for_aria()
    if not aria_ret_val:
        print("> Aria2c is missing from your system or path!")
        sys.exit(1)

    ffmpeg_ret_val = check_for_ffmpeg()
    if not ffmpeg_ret_val:
        print("> FFMPEG is missing from your system or path!")
        sys.exit(1)

    mp4decrypt_ret_val = check_for_mp4decrypt()
    if not mp4decrypt_ret_val:
        print(
            "> MP4Decrypt is missing from your system or path! (This is part of Bento4 tools)"
        )
        sys.exit(1)

def check_dirs():
    if not os.path.exists(saved_dir):
        os.makedirs(saved_dir)

    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

def load_keys():
    global keys
    f = open(keyfile_path, 'r')
    keys = json.loads(f.read())

def UdemyDownloader():
    global udemy, course, resource
    check_dirs()

     # warn that the keyfile is not found
    if not os.path.isfile(keyfile_path):
        print("!!! Keyfile not found! This means you probably didn't rename the keyfile correctly, DRM lecture decryption will fail! If you aren't downloading DRM encrypted courses, you can ignore this message. !!!")
        print("Waiting for 10 seconds...")
        time.sleep(10)

    load_keys()

    # ensure 3rd party binaries are installed
    ensure_dependencies_installed();

    # loads the .env file
    load_dotenv()

    # Creates a new parser and sets up the arguments
    setup_parser()

    # parses the arguments and sets all the variables
    args = parser.parse_args()
    process_args(args=args)

    udemy = Udemy(access_token=bearer_token)

    print("> Fetching course information, this may take a minute...")
    get_course_information()
    if not isinstance(course_info, dict):
        print("> Failed to get course information")
        sys.exit(1)
    print("> Course information retrieved!")

    if save_to_file:
        with open(course_info_path,
                  'w') as f:
            f.write(json.dumps(course_info))
            print("Saved course info to file")

    print("> Fetching course content, this may take a minute...")
    get_course_content()
    if not isinstance(course_content, dict):
        print("> Failed to get course content")
        sys.exit(1)
    print("> Course content retrieved!")

    if save_to_file:
        with open(course_content_path,
                  'w') as f:
            f.write(json.dumps(course_content))
            print("Saved course content to file")
    
    course = course_content.get("results")
    resource = course_content.get("detail")

    _udemy["access_token"] = access_token
    _udemy["course_id"] = course_id
    _udemy["title"] = title
    _udemy["course_title"] = course_title
    _udemy["chapters"] = []

    if resource:
        print("> Trying to logout")
        udemy.session.terminate()
        print("> Logged out.")

    if course:
        print("> Processing course data, this may take a minute. ")
        parse_data()

    if save_to_file:
        with open(_udemy_path,
                    'w') as f:
            f.write(json.dumps(_udemy))
            print("Saved parsed data to file")

    if print_info:
        _print_course_info()
    else:
        parse()


if __name__ == "__main__":
    UdemyDownloader()