# -*- coding: utf-8 -*-
import argparse
import glob
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
from html.parser import HTMLParser as compat_HTMLParser
from pathlib import Path
from typing import IO

import m3u8
import requests
import toml
import undetected_chromedriver as uc
import yt_dlp
from coloredlogs import ColoredFormatter
from pathvalidate import sanitize_filename
from requests.exceptions import ConnectionError as conn_error
from selenium.common.exceptions import ElementNotVisibleException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from _version import __version__
from constants import *
from tls import SSLCiphers
from utils import extract_kid, slow_type
from vtt_to_srt import convert

retry = 3
downloader = None
logger: logging.Logger = None
dl_assets = False
skip_lectures = False
dl_captions = False
caption_locale: str = "en"
quality = None
bearer_token: str = None
portal_name: str = None
course_name: str = None
keep_vtt = False
skip_hls = False
concurrent_downloads = 10
disable_ipv6 = False
save_to_file = None
load_from_file = None
course_url: str = None
info = None
keys = {}
id_as_course_name = False
is_subscription_course = False
use_h265 = False
h265_crf = 28
h265_preset = "medium"
use_nvenc = False
stream: logging.StreamHandler = None
username: str = None
password: str = None
headless = True
selenium = None


# from https://stackoverflow.com/a/21978778/9785713
def log_subprocess_output(prefix: str, pipe: IO[bytes]):
    if pipe:
        for line in iter(lambda: pipe.read(1), ""):
            logger.debug("[%s]: %r", prefix, line.decode("utf8").strip())
        pipe.flush()


def parse_config():
    global dl_assets, skip_lectures, dl_captions, caption_locale, quality, bearer_token, keep_vtt, skip_hls, concurrent_downloads, disable_ipv6, load_from_file, save_to_file, id_as_course_name, log_level, username, password, headless

    filename = "config.toml"
    if not os.path.isfile(filename):
        logger.warning("[-] Config file not found")
        return

    if os.path.isfile("config.dev.toml"):
        logger.info("[-] Using development config file")
        filename = "config.dev.toml"

    parsed_toml = toml.load(filename)
    general_config = parsed_toml.get("general", {})
    selenium_config = parsed_toml.get("selenium", {})

    dl_assets = general_config.get("download_assets", False)
    skip_lectures = general_config.get("skip_lectures", False)
    dl_captions = general_config.get("download_captions", False)
    caption_locale = general_config.get("caption_locale", "en")
    quality = general_config.get("quality", None)
    bearer_token = general_config.get("bearer_token", None)
    keep_vtt = general_config.get("keep_vtt", False)
    skip_hls = general_config.get("skip_hls", False)
    # TODO: add support for skipping dash streams
    skip_dash = general_config.get("skip_dash", False)
    concurrent_downloads = general_config.get("concurrent_downloads", 10)
    disable_ipv6 = general_config.get("disable_ipv6", False)
    load_from_file = general_config.get("load_from_file", None)
    save_to_file = general_config.get("save_to_file", None)
    id_as_course_name = general_config.get("id_as_course_name", False)
    log_level = general_config.get("log_level", "INFO")

    username = selenium_config.get("username", None)
    password = selenium_config.get("password", None)
    headless = selenium_config.get("headless", True)


def create_logger():
    global logger, stream
    logger = logging.getLogger(__name__)
    logging.root.setLevel(LOG_LEVEL)

    # create a colored formatter for the console
    console_formatter = ColoredFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    # create a regular non-colored formatter for the log file
    file_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # create a handler for console logging
    stream = logging.StreamHandler()
    stream.setLevel(LOG_LEVEL)
    stream.setFormatter(console_formatter)

    # create a handler for file logging
    file_handler = logging.FileHandler(LOG_FILE_PATH)
    file_handler.setFormatter(file_formatter)

    # construct the logger
    logger = logging.getLogger("udemy-downloader")
    logger.setLevel(LOG_LEVEL)
    logger.addHandler(stream)
    logger.addHandler(file_handler)


# this is the first function that is called, we parse the arguments, setup the logger, and ensure that required directories exist
def pre_run():
    global dl_assets, skip_lectures, dl_captions, caption_locale, quality, portal_name, course_name, keep_vtt, skip_hls, concurrent_downloads, disable_ipv6, load_from_file, save_to_file, bearer_token, course_url, info, logger, keys, id_as_course_name, is_subscription_course, log_level, use_h265, h265_crf, h265_preset, use_nvenc, username, password

    # make sure the logs directory exists
    if not os.path.exists(LOG_DIR_PATH):
        os.makedirs(LOG_DIR_PATH, exist_ok=True)

    # setup a logger
    create_logger()

    # load config.toml and set initial settings
    parse_config()

    # make sure the directory exists
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    parser = argparse.ArgumentParser(description="Udemy Downloader")
    parser.add_argument("-c", "--course-url", dest="course_url", type=str, help="The URL of the course to download", required=True)
    parser.add_argument(
        "-b",
        "--bearer",
        dest="bearer_token",
        type=str,
        help="The Bearer token to use",
    )
    parser.add_argument(
        "-u",
        "--username",
        dest="username",
        type=str,
        help="username",
    )
    parser.add_argument(
        "-p",
        "--password",
        dest="password",
        type=str,
        help="password",
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
        "--concurrent-downloads",
        dest="concurrent_downloads",
        type=int,
        help="The number of maximum concurrent downloads for segments (HLS and DASH, must be a number 1-30)",
    )
    parser.add_argument(
        "--disable-ipv6",
        dest="disable_ipv6",
        action="store_true",
        help="If specified, ipv6 will be disabled in aria2",
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
        dest="info",
        action="store_true",
        help="If specified, only course information will be printed, nothing will be downloaded",
    )
    parser.add_argument(
        "--id-as-course-name",
        dest="id_as_course_name",
        action="store_true",
        help="If specified, the course id will be used in place of the course name for the output directory. This is a 'hack' to reduce the path length",
    )
    parser.add_argument(
        "-sc",
        "--subscription-course",
        dest="is_subscription_course",
        action="store_true",
        help="If this course is part of a subscription plan (Personal or Pro Plans)",
    )

    parser.add_argument(
        "--save-to-file",
        dest="save_to_file",
        action="store_true",
        help="If specified, course content will be saved to a file that can be loaded later with --load-from-file, this can reduce processing time (Note that asset links expire after a certain amount of time)",
    )
    parser.add_argument(
        "--load-from-file",
        dest="load_from_file",
        action="store_true",
        help="If specified, course content will be loaded from a previously saved file with --save-to-file, this can reduce processing time (Note that asset links expire after a certain amount of time)",
    )
    parser.add_argument(
        "--log-level",
        dest="log_level",
        type=str,
        help="Logging level: one of DEBUG, INFO, ERROR, WARNING, CRITICAL (Default is INFO)",
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
        "--use-nvenc",
        dest="use_nvenc",
        action="store_true",
        help="Whether to use the NVIDIA hardware transcoding for H.265. Only works if you have a supported NVIDIA GPU and ffmpeg with nvenc support",
    )
    parser.add_argument("-v", "--version", action="version", version="You are running version {version}".format(version=__version__))

    # parse command line arguments, these override the config file settings
    args = parser.parse_args()
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
    if args.concurrent_downloads:
        concurrent_downloads = args.concurrent_downloads

        if concurrent_downloads <= 0:
            # if the user gave a number that is less than or equal to 0, set cc to default of 10
            concurrent_downloads = 10
        elif concurrent_downloads > 30:
            # if the user gave a number thats greater than 30, set cc to the max of 30
            concurrent_downloads = 30
    if args.disable_ipv6:
        disable_ipv6 = args.disable_ipv6
    if args.load_from_file:
        load_from_file = args.load_from_file
    if args.save_to_file:
        save_to_file = args.save_to_file
    if args.bearer_token:
        bearer_token = args.bearer_token
    if args.course_url:
        course_url = args.course_url
    if args.info:
        info = args.info
    if args.use_h265:
        use_h265 = True
    if args.h265_crf:
        h265_crf = args.h265_crf
    if args.h265_preset:
        h265_preset = args.h265_preset
    if args.use_nvenc:
        use_nvenc = True
    if args.log_level:
        log_level = args.log_level
    if args.id_as_course_name:
        id_as_course_name = args.id_as_course_name
    if args.is_subscription_course:
        is_subscription_course = args.is_subscription_course
    if args.username:
        username = args.username
    if args.password:
        password = args.password

    # parse loglevel string to int
    if log_level.upper() == "DEBUG":
        logger.setLevel(logging.DEBUG)
        stream.setLevel(logging.DEBUG)
    elif log_level.upper() == "INFO":
        logger.setLevel(logging.INFO)
        stream.setLevel(logging.INFO)
    elif log_level.upper() == "ERROR":
        logger.setLevel(logging.ERROR)
        stream.setLevel(logging.ERROR)
    elif log_level.upper() == "WARNING":
        logger.setLevel(logging.WARNING)
        stream.setLevel(logging.WARNING)
    elif log_level.upper() == "CRITICAL":
        logger.setLevel(logging.CRITICAL)
        stream.setLevel(logging.CRITICAL)
    else:
        logger.warning("Invalid log level: %s; Using INFO", args.log_level)
        logger.setLevel(logging.INFO)
        stream.setLevel(logging.INFO)

    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(SAVED_DIR).mkdir(parents=True, exist_ok=True)

    # Get the keys
    if os.path.exists(KEY_FILE_PATH):
        with open(KEY_FILE_PATH, encoding="utf8", mode="r") as keyfile:
            keys = json.loads(keyfile.read())
    else:
        logger.warning("> Keyfile not found! You won't be able to decrypt videos!")


class Selenium:
    def __init__(self):
        data_dir = os.path.join(os.getcwd(), "selenium_data")
        options = ChromeOptions()
        options.add_argument("--profile=Selenium")
        options.add_argument(f"--user-data-dir={data_dir}")
        self._driver = uc.Chrome(options=options, headless=headless)

    @property
    def driver(self):
        return self._driver


class Udemy:
    def __init__(self, bearer_token):
        self.session = None
        self.bearer_token = None
        self.auth = UdemyAuth(cache_session=False)
        if not self.session:
            self.session, self.bearer_token = self.auth.authenticate(bearer_token=bearer_token)

        if not is_subscription_course:
            if self.session and self.bearer_token:
                self.session._headers.update({"Authorization": "Bearer {}".format(self.bearer_token)})
                self.session._headers.update({"X-Udemy-Authorization": "Bearer {}".format(self.bearer_token)})
                logger.info("[+] Login Success")
            else:
                logger.fatal("[-] Login Failure! You are probably missing an access token!")
                sys.exit(1)

    def _extract_supplementary_assets(self, supp_assets, lecture_counter):
        _temp = []
        for entry in supp_assets:
            title = sanitize_filename(entry.get("title"))
            filename = entry.get("filename")
            download_urls = entry.get("download_urls")
            external_url = entry.get("external_url")
            asset_type = entry.get("asset_type").lower()
            id = entry.get("id")
            if asset_type == "file":
                if download_urls and isinstance(download_urls, dict):
                    extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
                    download_url = download_urls.get("File", [])[0].get("file")
                    _temp.append({"type": "file", "title": title, "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
            elif asset_type == "sourcecode":
                if download_urls and isinstance(download_urls, dict):
                    extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
                    download_url = download_urls.get("SourceCode", [])[0].get("file")
                    _temp.append({"type": "source_code", "title": title, "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
            elif asset_type == "externallink":
                _temp.append({"type": "external_link", "title": title, "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": "txt", "download_url": external_url, "id": id})
        return _temp

    def _extract_ppt(self, asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("Presentation", [])[0].get("file")
            _temp.append({"type": "presentation", "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
        return _temp

    def _extract_file(self, asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("File", [])[0].get("file")
            _temp.append({"type": "file", "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
        return _temp

    def _extract_ebook(self, asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("E-Book", [])[0].get("file")
            _temp.append({"type": "ebook", "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
        return _temp

    def _extract_audio(self, asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("Audio", [])[0].get("file")
            _temp.append({"type": "audio", "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
        return _temp

    def _extract_sources(self, sources, skip_hls):
        _temp = []
        if sources and isinstance(sources, list):
            for source in sources:
                label = source.get("label")
                download_url = source.get("file")
                if not download_url:
                    continue
                if label.lower() == "audio":
                    continue
                height = label if label else None
                if height == "2160":
                    width = "3840"
                elif height == "1440":
                    width = "2560"
                elif height == "1080":
                    width = "1920"
                elif height == "720":
                    width = "1280"
                elif height == "480":
                    width = "854"
                elif height == "360":
                    width = "640"
                elif height == "240":
                    width = "426"
                else:
                    width = "256"
                if source.get("type") == "application/x-mpegURL" or "m3u8" in download_url:
                    if not skip_hls:
                        out = self._extract_m3u8(download_url)
                        if out:
                            _temp.extend(out)
                else:
                    _type = source.get("type")
                    _temp.append(
                        {
                            "type": "video",
                            "height": height,
                            "width": width,
                            "extension": _type.replace("video/", ""),
                            "download_url": download_url,
                        }
                    )
        return _temp

    def _extract_media_sources(self, sources):
        _temp = []
        if sources and isinstance(sources, list):
            for source in sources:
                _type = source.get("type")
                src = source.get("src")

                if _type == "application/dash+xml":
                    out = self._extract_mpd(src)
                    if out:
                        _temp.extend(out)
        return _temp

    def _extract_subtitles(self, tracks):
        _temp = []
        if tracks and isinstance(tracks, list):
            for track in tracks:
                if not isinstance(track, dict):
                    continue
                if track.get("_class") != "caption":
                    continue
                download_url = track.get("url")
                if not download_url or not isinstance(download_url, str):
                    continue
                lang = track.get("language") or track.get("srclang") or track.get("label") or track["locale_id"].split("_")[0]
                ext = "vtt" if "vtt" in download_url.rsplit(".", 1)[-1] else "srt"
                _temp.append(
                    {
                        "type": "subtitle",
                        "language": lang,
                        "extension": ext,
                        "download_url": download_url,
                    }
                )
        return _temp

    def _extract_m3u8(self, url):
        """extracts m3u8 streams"""
        asset_id_re = re.compile(r"assets/(?P<id>\d+)/")
        _temp = []

        # get temp folder
        temp_path = Path(Path.cwd(), "temp")

        # ensure the folder exists
        temp_path.mkdir(parents=True, exist_ok=True)

        # # extract the asset id from the url
        asset_id = asset_id_re.search(url).group("id")

        m3u8_path = Path(temp_path, f"index_{asset_id}.m3u8")

        try:
            r = self.session._get(url)
            r.raise_for_status()
            raw_data = r.text

            # write to temp file for later
            with open(m3u8_path, "w") as f:
                f.write(r.text)

            m3u8_object = m3u8.loads(raw_data)
            playlists = m3u8_object.playlists
            seen = set()
            for pl in playlists:
                resolution = pl.stream_info.resolution
                codecs = pl.stream_info.codecs

                if not resolution:
                    continue
                if not codecs:
                    continue
                width, height = resolution

                if height in seen:
                    continue

                # we need to save the individual playlists to disk also
                playlist_path = Path(temp_path, f"index_{asset_id}_{width}x{height}.m3u8")

                with open(playlist_path, "w") as f:
                    r = self.session._get(pl.uri)
                    r.raise_for_status()
                    f.write(r.text)

                seen.add(height)
                _temp.append(
                    {
                        "type": "hls",
                        "height": height,
                        "width": width,
                        "extension": "mp4",
                        "download_url": playlist_path.as_uri(),
                    }
                )
        except Exception as error:
            logger.error(f"[-] Udemy Says : '{error}' while fetching hls streams..")
        return _temp

    def _extract_mpd(self, url):
        """extracts mpd streams"""
        asset_id_re = re.compile(r"assets/(?P<id>\d+)/")
        _temp = []

        # get temp folder
        temp_path = Path(Path.cwd(), "temp")

        # ensure the folder exists
        temp_path.mkdir(parents=True, exist_ok=True)

        # # extract the asset id from the url
        asset_id = asset_id_re.search(url).group("id")

        # download the mpd and save it to the temp file
        mpd_path = Path(temp_path, f"index_{asset_id}.mpd")

        try:
            with open(mpd_path, "wb") as f:
                r = self.session._get(url)
                r.raise_for_status()
                f.write(r.content)

            ytdl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "allow_unplayable_formats": True, "enable_file_urls": True})
            results = ytdl.extract_info(mpd_path.as_uri(), download=False, force_generic_extractor=True)
            seen = set()
            formats = results.get("formats")

            format_id = results.get("format_id")
            best_audio_format_id = format_id.split("+")[1]
            # I forget what this was for
            # best_audio = next((x for x in formats
            #                    if x.get("format_id") == best_audio_format_id),
            #                   None)
            for f in formats:
                if "video" in f.get("format_note"):
                    # is a video stream
                    format_id = f.get("format_id")
                    extension = f.get("ext")
                    height = f.get("height")
                    width = f.get("width")

                    if height and height not in seen:
                        seen.add(height)
                        _temp.append(
                            {
                                "type": "dash",
                                "height": str(height),
                                "width": str(width),
                                "format_id": f"{format_id},{best_audio_format_id}",
                                "extension": extension,
                                "download_url": f.get("manifest_url"),
                            }
                        )
                # ignore audio tracks
                elif "audio" not in f.get("format_note"):
                    # unknown format type
                    logger.debug(f"[-] Unknown format type : {f}")
                    continue
        except Exception:
            logger.exception(f"[-] Error fetching MPD streams")
        return _temp

    def extract_course_name(self, url):
        """
        @author r0oth3x49
        """
        obj = re.search(
            r"(?i)(?://(?P<portal_name>.+?).udemy.com/(?:course(/draft)*/)?(?P<name_or_id>[a-zA-Z0-9_-]+))",
            url,
        )
        if obj:
            return obj.group("portal_name"), obj.group("name_or_id")

    def extract_portal_name(self, url):
        obj = re.search(r"(?i)(?://(?P<portal_name>.+?).udemy.com)", url)
        if obj:
            return obj.group("portal_name")

    def _subscribed_courses(self, portal_name, course_name):
        results = []
        self.session._headers.update(
            {
                "Host": "{portal_name}.udemy.com".format(portal_name=portal_name),
                "Referer": "https://{portal_name}.udemy.com/home/my-courses/search/?q={course_name}".format(portal_name=portal_name, course_name=course_name),
            }
        )
        url = COURSE_SEARCH.format(portal_name=portal_name, course_name=course_name)
        try:
            webpage = self.session._get(url).content
            webpage = webpage.decode("utf8", "ignore")
            webpage = json.loads(webpage)
        except conn_error as error:
            logger.fatal(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            logger.fatal(f"Udemy Says: {error} on {url}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
        return results

    def _extract_course_info_json(self, url, course_id, portal_name):
        self.session._headers.update({"Referer": url})
        url = COURSE_INFO_URL.format(portal_name=portal_name, course_id=course_id)
        try:
            resp = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"[-] Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            return resp

    def _extract_course_json(self, url, course_id, portal_name):
        self.session._headers.update({"Referer": url})
        url = COURSE_URL.format(portal_name=portal_name, course_id=course_id)
        try:
            resp = self.session._get(url)
            if resp.status_code in [502, 503, 504]:
                logger.info("> The course content is large, using large content extractor...")
                resp = self._extract_large_course_content(url=url)
            else:
                resp = resp.json()
                e = resp.get("error")
                if e:
                    status_code = e.get("status_code")
                    message = e.get("message")
                    if status_code in [502, 503, 504]:
                        logger.info(f"Looks like a large course: [{status_code}] {message}")
                        resp = self._extract_large_course_content(url=url)
                    else:
                        logger.fatal(f"Error: [{status_code}] {message}")
                        time.sleep(0.8)
                        sys.exit(1)
        except conn_error as error:
            logger.fatal(f"[-] Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception):
            resp = self._extract_large_course_content(url=url)
            return resp
        else:
            return resp

    def _extract_course_json_sub(self, selenium: Selenium, course_id: str, portal_name: str):
        url = COURSE_URL.format(portal_name=portal_name, course_id=course_id)
        selenium.driver.get(url)
        # TODO: actually wait for an element
        time.sleep(2)

        if "Attention" in selenium.driver.title:
            # cloudflare captcha, panic
            raise Exception("[-] Cloudflare captcha detected!")

        # wait for page load
        WebDriverWait(selenium.driver, 60).until(
            EC.visibility_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)

        body_text = selenium.driver.find_element(By.TAG_NAME, "body").text
        if not body_text:
            raise Exception("[-] Could not get page body text!")
        if "502 Bad Gateway" in body_text:
            # its a large course, handle accordingly
            logger.info("[+] Detected large course content, using large content extractor...")
            return self._extract_large_course_content_sub(url=url, selenium=selenium)
        else:
            # get the text from the page
            page_text = selenium.driver.find_element(By.TAG_NAME, "pre").text
            if not page_text or not isinstance(page_text, str):
                raise Exception("[-] Could not get page pre text!")
            page_json = json.loads(page_text)
            if page_json:
                return page_json
            else:
                logger.error("[-] Failed to extract course json!")
                time.sleep(0.8)
                sys.exit(1)

    def _extract_large_course_content(self, url):
        url = url.replace("10000", "50") if url.endswith("10000") else url
        try:
            data = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"[-] Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            _next = data.get("next")
            while _next:
                logger.info("> Downloading course information.. ")
                try:
                    resp = self.session._get(_next).json()
                except conn_error as error:
                    logger.fatal(f"[-] Udemy Says: Connection error, {error}")
                    time.sleep(0.8)
                    sys.exit(1)
                else:
                    _next = resp.get("next")
                    results = resp.get("results")
                    if results and isinstance(results, list):
                        for d in resp["results"]:
                            data["results"].append(d)
            return data

    def _extract_large_course_content_sub(self, url, selenium: Selenium):
        url = url.replace("10000", "50") if url.endswith("10000") else url
        try:
            selenium.driver.get(url)
            time.sleep(2)

            if "Attention" in selenium.driver.title:
                # cloudflare captcha, panic
                raise Exception("[-] Cloudflare captcha detected!")

            # wait for page load
            WebDriverWait(selenium.driver, 60).until(
                EC.visibility_of_element_located((By.TAG_NAME, "body")))
            time.sleep(2)

            # get the text from the page
            page_text = selenium.driver.find_element(By.TAG_NAME, "pre").text
            if not page_text or not isinstance(page_text, str):
                raise Exception("[-] Could not get page pre text!")
            data = json.loads(page_text)
            logger.debug(data)

        except conn_error as error:
            logger.fatal(f"[-] Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            _next = data.get("next")
            while _next:
                logger.info("> Downloading course information.. ")
                try:
                    selenium.driver.get(_next)
                    time.sleep(2)

                    if "Attention" in selenium.driver.title:
                        # cloudflare captcha, panic
                        raise Exception("[-] Cloudflare captcha detected!")

                    # wait for page load
                    WebDriverWait(selenium.driver, 60).until(
                        EC.visibility_of_element_located((By.TAG_NAME, "body")))
                    time.sleep(2)

                    # get the text from the page
                    page_text = selenium.driver.find_element(
                        By.TAG_NAME, "pre").text
                    if not page_text or not isinstance(page_text, str):
                        raise Exception("[-] Could not get page pre text!")
                    resp = json.loads(page_text)
                    logger.debug(resp)
                except conn_error as error:
                    logger.fatal(f"[-] Udemy Says: Connection error, {error}")
                    time.sleep(0.8)
                    sys.exit(1)
                else:
                    _next = resp.get("next")
                    results = resp.get("results")
                    if results and isinstance(results, list):
                        for d in resp["results"]:
                            data["results"].append(d)
            return data

    def _extract_course(self, response, course_name):
        _temp = {}
        if response:
            for entry in response:
                course_id = str(entry.get("id"))
                published_title = entry.get("published_title")
                if course_name in (published_title, course_id):
                    _temp = entry
                    break
        return _temp

    def _my_courses(self, portal_name):
        results = []
        try:
            url = MY_COURSES_URL.format(portal_name=portal_name)
            webpage = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            logger.fatal(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
        return results

    def _subscribed_collection_courses(self, portal_name):
        url = COLLECTION_URL.format(portal_name=portal_name)
        courses_lists = []
        try:
            webpage = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            logger.fatal(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
            if results:
                [courses_lists.extend(courses.get("courses", [])) for courses in results if courses.get("courses", [])]
        return courses_lists

    def _archived_courses(self, portal_name):
        results = []
        try:
            url = MY_COURSES_URL.format(portal_name=portal_name)
            url = f"{url}&is_archived=true"
            webpage = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            logger.fatal(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
        return results

    def _my_courses(self, portal_name):
        results = []
        try:
            url = MY_COURSES_URL.format(portal_name=portal_name)
            webpage = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            logger.fatal(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
        return results

    def _subscribed_collection_courses(self, portal_name):
        url = COLLECTION_URL.format(portal_name=portal_name)
        courses_lists = []
        try:
            webpage = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            logger.fatal(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
            if results:
                [courses_lists.extend(courses.get("courses", [])) for courses in results if courses.get("courses", [])]
        return courses_lists

    def _archived_courses(self, portal_name):
        results = []
        try:
            url = MY_COURSES_URL.format(portal_name=portal_name)
            url = f"{url}&is_archived=true"
            webpage = self.session._get(url).json()
        except conn_error as error:
            logger.fatal(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            logger.fatal(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
        return results

    def _extract_course_info(self, url):
        portal_name, course_name = self.extract_course_name(url)
        course = {}
        results = self._subscribed_courses(portal_name=portal_name, course_name=course_name)
        course = self._extract_course(response=results, course_name=course_name)
        if not course:
            results = self._my_courses(portal_name=portal_name)
            course = self._extract_course(response=results, course_name=course_name)
        if not course:
            results = self._subscribed_collection_courses(portal_name=portal_name)
            course = self._extract_course(response=results, course_name=course_name)
        if not course:
            results = self._archived_courses(portal_name=portal_name)
            course = self._extract_course(response=results, course_name=course_name)

        if course:
            course.update({"portal_name": portal_name})
            return course.get("id"), course
        if not course:
            logger.fatal("Downloading course information, course id not found .. ")
            logger.fatal(
                "It seems either you are not enrolled or you have to visit the course atleast once while you are logged in.",
            )
            logger.info(
                "Trying to logout now...",
            )
            self.session.terminate()
            logger.info(
                "Logged out successfully.",
            )
            sys.exit(1)

    def _parse_lecture(self, lecture: dict):
        retVal = []

        index = lecture.get("index")  # this is lecture_counter
        lecture_data = lecture.get("data")
        asset = lecture_data.get("asset")
        supp_assets = lecture_data.get("supplementary_assets")

        if isinstance(asset, dict):
            asset_type = asset.get("asset_type").lower() or asset.get("assetType").lower
            if asset_type == "article":
                if isinstance(supp_assets, list) and len(supp_assets) > 0:
                    retVal = self._extract_supplementary_assets(supp_assets, index)
            elif asset_type == "video":
                if isinstance(supp_assets, list) and len(supp_assets) > 0:
                    retVal = self._extract_supplementary_assets(supp_assets, index)
            elif asset_type == "e-book":
                retVal = self._extract_ebook(asset, index)
            elif asset_type == "file":
                retVal = self._extract_file(asset, index)
            elif asset_type == "presentation":
                retVal = self._extract_ppt(asset, index)
            elif asset_type == "audio":
                retVal = self._extract_audio(asset, index)
            else:
                logger.warning(f"Unknown asset type: {asset_type}")

        stream_urls = asset.get("stream_urls")
        if stream_urls != None:
            # not encrypted
            if stream_urls and isinstance(stream_urls, dict):
                sources = stream_urls.get("Video")
                tracks = asset.get("captions")
                # duration = asset.get("time_estimation")
                sources = self._extract_sources(sources, skip_hls)
                subtitles = self._extract_subtitles(tracks)
                sources_count = len(sources)
                subtitle_count = len(subtitles)
                lecture.pop("data")  # remove the raw data object after processing
                lecture = {
                    **lecture,
                    "assets": retVal,
                    "assets_count": len(retVal),
                    "sources": sources,
                    "subtitles": subtitles,
                    "subtitle_count": subtitle_count,
                    "sources_count": sources_count,
                    "is_encrypted": False,
                    "asset_id": asset.get("id"),
                }
            else:
                lecture.pop("data")  # remove the raw data object after processing
                lecture = {
                    **lecture,
                    "html_content": asset.get("body"),
                    "extension": "html",
                    "assets": retVal,
                    "assets_count": len(retVal),
                    "subtitle_count": 0,
                    "sources_count": 0,
                    "is_encrypted": False,
                    "asset_id": asset.get("id"),
                }
        else:
            # encrypted
            media_sources = asset.get("media_sources")
            if media_sources and isinstance(media_sources, list):
                sources = self._extract_media_sources(media_sources)
                tracks = asset.get("captions")
                # duration = asset.get("time_estimation")
                subtitles = self._extract_subtitles(tracks)
                sources_count = len(sources)
                subtitle_count = len(subtitles)
                lecture.pop("data")  # remove the raw data object after processing
                lecture = {
                    **lecture,
                    # "duration": duration,
                    "assets": retVal,
                    "assets_count": len(retVal),
                    "video_sources": sources,
                    "subtitles": subtitles,
                    "subtitle_count": subtitle_count,
                    "sources_count": sources_count,
                    "is_encrypted": True,
                    "asset_id": asset.get("id"),
                }

            else:
                lecture.pop("data")  # remove the raw data object after processing
                lecture = {
                    **lecture,
                    "html_content": asset.get("body"),
                    "extension": "html",
                    "assets": retVal,
                    "assets_count": len(retVal),
                    "subtitle_count": 0,
                    "sources_count": 0,
                    "is_encrypted": False,
                    "asset_id": asset.get("id"),
                }

        return lecture
    def _selenium_login(self, selenium: Selenium, portal_name: str):
        # go to the login page
        selenium.driver.get(LOGIN_URL.format(portal_name=portal_name))

        # wait for the page to load, we need to see the id_name element on the page.
        WebDriverWait(selenium.driver, 60).until(EC.presence_of_element_located((By.NAME, "email")))

        # find the email, password, and submit button
        email_elem = selenium.driver.find_element(By.NAME, "email")
        password_elem = selenium.driver.find_element(By.NAME, "password")
        submit_btn_elem = selenium.driver.find_element(By.XPATH, '//*[@id="udemy"]/div[1]/div[2]/div/div/form/button')

        # select the email field and enter the email
        ActionChains(selenium.driver).move_to_element(email_elem).click().perform()
        email_elem.clear()
        slow_type(email_elem, username)

        # select the password field and enter the password
        ActionChains(selenium.driver).move_to_element(password_elem).click().perform()
        password_elem.clear()
        slow_type(password_elem, password)

        # click the submit button
        ActionChains(selenium.driver).move_to_element(submit_btn_elem).click().perform()

        # TODO: handle failed logins

        # wait for the page to load
        WebDriverWait(selenium.driver, 60).until(EC.title_contains("Online Courses - Learn Anything, On Your Schedule | Udemy"))

    def _extract_course_info_sub(self, selenium: Selenium, course_url: str):
        """
        Extract course information for subscription based courses use selenium
        """
        portal_name = self.extract_portal_name(course_url)
        portal_url = PORTAL_HOME.format(portal_name=portal_name)
        selenium.driver.get(portal_url)
        
        # wait for the page to load
        WebDriverWait(selenium.driver, 60).until(EC.title_contains("Online Courses - Learn Anything, On Your Schedule | Udemy"))
        # we need to check if we are logged in or not
        is_authenticated = selenium.driver.execute_script("return window.UD.me.is_authenticated")
        print("Is Authenticated: " + str(is_authenticated))
        if not is_authenticated:
            if not username or not password:
                logger.fatal("Username or password not provided, cannot continue")
                selenium.driver.quit()
                sys.exit(1)
            self._selenium_login(selenium, portal_name)

        # go to the course page
        selenium.driver.get(course_url)

        # wait for either the body to be loaded or for the title to contain Attention (cloudflare captcha)
        WebDriverWait(selenium.driver, 60).until(
            EC.presence_of_element_located((By.CLASS_NAME, "ud-component--course-taking--app")) or EC.title_contains("Attention")
        )

        # check if we get a cloudflare captcha
        if "Attention" in selenium.driver.title:
            # cloudflare captcha, panic
            raise Exception("Cloudflare captcha detected!")

        # get the body element
        data = selenium.driver.find_element(By.CLASS_NAME, "ud-component--course-taking--app")
        # extract the course data attribute
        data_args = data.get_attribute("data-module-args")
        data_args = data_args.replace("quot;", '"')
        data_json = json.loads(data_args)
        course_id = data_json.get("courseId", None)

        # go to the course info json page
        course_url = COURSE_INFO_URL.format(portal_name=portal_name, course_id=course_id)
        selenium.driver.get(course_url)
        # wait for pre tag
        WebDriverWait(selenium.driver, 60).until(EC.visibility_of_element_located((By.TAG_NAME, "pre")))
        
        # get the text from the page
        page_text = selenium.driver.find_element(By.TAG_NAME, "pre").text
        if not page_text or not isinstance(page_text, str):
            raise Exception("[-] Could not get page text!")
        course = json.loads(page_text)
        course.update({"portal_name": portal_name})
        return course_id, course

        
class Session(object):
    def __init__(self):
        self._headers = HEADERS
        self._session = requests.sessions.Session()
        self._session.mount(
            "https://",
            SSLCiphers(
                cipher_list="ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-SHA256:AES256-SH"
            ),
        )

    def _set_auth_headers(self, bearer_token=""):
        self._headers["Authorization"] = "Bearer {}".format(bearer_token)
        self._headers["X-Udemy-Authorization"] = "Bearer {}".format(bearer_token)

    def _get(self, url):
        for i in range(10):
            session = self._session.get(url, headers=self._headers)
            if session.ok or session.status_code in [502, 503]:
                return session
            if not session.ok:
                logger.error(f"[-] Failed request: {url}")
                logger.debug(session.text)
                logger.error(f"[-] {session.status_code} {session.reason}, retrying (attempt {i} )...")
                time.sleep(0.8)

    def _post(self, url, data, redirect=True):
        session = self._session.post(url, data, headers=self._headers, allow_redirects=redirect)
        if session.ok:
            return session
        if not session.ok:
            raise Exception(f"{session.status_code} {session.reason}")

    def terminate(self):
        self._set_auth_headers()
        return


# Thanks to a great open source utility youtube-dl ..
class HTMLAttributeParser(compat_HTMLParser):  # pylint: disable=W
    """Trivial HTML parser to gather the attributes for a single element"""

    def __init__(self):
        self.attrs = {}
        compat_HTMLParser.__init__(self)

    def handle_starttag(self, tag, attrs):
        self.attrs = dict(attrs)


def extract_attributes(html_element):
    """Given a string for an HTML element such as
    <el
         a="foo" B="bar" c="&98;az" d=boz
         empty= noval entity="&amp;"
         sq='"' dq="'"
    >
    Decode and return a dictionary of attributes.
    {
        'a': 'foo', 'b': 'bar', c: 'baz', d: 'boz',
        'empty': '', 'noval': None, 'entity': '&',
        'sq': '"', 'dq': '\''
    }.
    NB HTMLParser is stricter in Python 2.6 & 3.2 than in later versions,
    but the cases in the unit test will work for all of 2.6, 2.7, 3.2-3.5.
    """
    parser = HTMLAttributeParser()
    try:
        parser.feed(html_element)
        parser.close()
    except Exception:  # pylint: disable=W
        pass
    return parser.attrs


def hidden_inputs(html):
    html = re.sub(r"<!--(?:(?!<!--).)*-->", "", html)
    hidden_inputs = {}  # pylint: disable=W
    for entry in re.findall(r"(?i)(<input[^>]+>)", html):
        attrs = extract_attributes(entry)
        if not entry:
            continue
        if attrs.get("type") not in ("hidden", "submit"):
            continue
        name = attrs.get("name") or attrs.get("id")
        value = attrs.get("value")
        if name and value is not None:
            hidden_inputs[name] = value
    return hidden_inputs


def search_regex(pattern, string, name, default=object(), fatal=True, flags=0, group=None):
    """
    Perform a regex search on the given string, using a single or a list of
    patterns returning the first matching group.
    In case of failure return a default value or raise a WARNING or a
    RegexNotFoundError, depending on fatal, specifying the field name.
    """
    if isinstance(pattern, str):
        mobj = re.search(pattern, string, flags)
    else:
        for p in pattern:
            mobj = re.search(p, string, flags)
            if mobj:
                break

    _name = name

    if mobj:
        if group is None:
            # return the first matching group
            return next(g for g in mobj.groups() if g is not None)
        else:
            return mobj.group(group)
    elif default is not object():
        return default
    elif fatal:
        logger.fatal("[-] Unable to extract %s" % _name)
        exit(0)
    else:
        logger.fatal("[-] unable to extract %s" % _name)
        exit(0)


class UdemyAuth(object):
    def __init__(self, username="", password="", cache_session=False):
        self.username = username
        self.password = password
        self._cache = cache_session
        self._session = Session()

    def authenticate(self, bearer_token=""):
        if bearer_token:
            self._session._set_auth_headers(bearer_token=bearer_token)
            self._session._session.cookies.update({"bearer_token": bearer_token})
            return self._session, bearer_token
        else:
            self._session._set_auth_headers()
            return self._session, None


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
        total_time = float(str((day * 24 * 60 * 60) + (hour * 60 * 60) + (minute * 60) + (int(second.split(".")[0]))) + "." + str(int(second.split(".")[-1])))
        return total_time

    else:
        logger.error("[-] Duration Format Error")
        return None


def cleanup(path):
    """
    @author Jayapraveen
    """
    leftover_files = glob.glob(path + "/*.mp4", recursive=True)
    for file_list in leftover_files:
        try:
            os.remove(file_list)
        except OSError:
            logger.exception(f"Error deleting file: {file_list}")
    os.removedirs(path)


def mux_process(video_title, video_filepath, audio_filepath, output_path):
    """
    @author Jayapraveen
    """
    codec = "hevc_nvenc" if use_nvenc else "libx265"
    transcode = "-hwaccel cuda -hwaccel_output_format cuda" if use_nvenc else []
    if os.name == "nt":
        if use_h265:
            command = 'ffmpeg {} -y -i "{}" -i "{}" -c:v {} -vtag hvc1 -crf {} -preset {} -c:a copy -fflags +bitexact -map_metadata -1 -metadata title="{}" "{}"'.format(
                transcode, video_filepath, audio_filepath, codec, h265_crf, h265_preset, video_title, output_path
            )
        else:
            command = 'ffmpeg -y -i "{}" -i "{}" -c:v copy -c:a copy -fflags +bitexact -map_metadata -1 -metadata title="{}" "{}"'.format(video_filepath, audio_filepath, video_title, output_path)
    else:
        if use_h265:
            command = 'nice -n 7 ffmpeg {} -y -i "{}" -i "{}" -c:v libx265 -vtag hvc1 -crf {} -preset {} -c:a copy -fflags +bitexact -map_metadata -1 -metadata title="{}" "{}"'.format(
                transcode, video_filepath, audio_filepath, codec, h265_crf, h265_preset, video_title, output_path
            )
        else:
            command = 'nice -n 7 ffmpeg -y -i "{}" -i "{}" -c:v copy -c:a copy -fflags +bitexact -map_metadata -1 -metadata title="{}" "{}"'.format(
                video_filepath, audio_filepath, video_title, output_path
            )

    process = subprocess.Popen(command, shell=True)
    log_subprocess_output("FFMPEG-STDOUT", process.stdout)
    log_subprocess_output("FFMPEG-STDERR", process.stderr)
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception("Muxing returned a non-zero exit code")

    return ret_code


def decrypt(kid, in_filepath, out_filepath):
    try:
        key = keys[kid.lower()]
    except KeyError:
        raise KeyError("[-] Key not found")

    if os.name == "nt":
        command = f'shaka-packager --enable_raw_key_decryption --keys key_id={kid}:key={key} input="{in_filepath}",stream_selector="0",output="{out_filepath}"'
    else:
        command = f'nice -n 7 shaka-packager --enable_raw_key_decryption --keys key_id={kid}:key={key} input="{in_filepath}",stream_selector="0",output="{out_filepath}"'

    process = subprocess.Popen(command, shell=True)
    log_subprocess_output("SHAKA-STDOUT", process.stdout)
    log_subprocess_output("SHAKA-STDERR", process.stderr)
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception("Decryption returned a non-zero exit code")

    return ret_code


def handle_segments(url, format_id, video_title, output_path, lecture_file_name, chapter_dir):
    os.chdir(os.path.join(chapter_dir))
    # for french language among others, this characters cause problems with shaka-packager resulting in decryption failure
    # https://github.com/Puyodead1/udemy-downloader/issues/137
    # Thank to cutecat !
    lecture_file_name = (
        lecture_file_name.replace("é", "e")
        .replace("è", "e")
        .replace("à", "a")
        .replace("À", "A")
        .replace("à", "a")
        .replace("Á", "A")
        .replace("á", "a")
        .replace("Â", "a")
        .replace("â", "a")
        .replace("Ã", "A")
        .replace("ã", "a")
        .replace("Ä", "A")
        .replace("ä", "a")
        .replace("Å", "A")
        .replace("å", "a")
        .replace("Æ", "AE")
        .replace("æ", "ae")
        .replace("Ç", "C")
        .replace("ç", "c")
        .replace("Ð", "D")
        .replace("ð", "o")
        .replace("È", "E")
        .replace("è", "e")
        .replace("É", "e")
        .replace("Ê", "e")
        .replace("ê", "e")
        .replace("Ë", "E")
        .replace("ë", "e")
        .replace("Ì", "I")
        .replace("ì", "i")
        .replace("Í", "I")
        .replace("í", "I")
        .replace("Î", "I")
        .replace("î", "i")
        .replace("Ï", "I")
        .replace("ï", "i")
        .replace("Ñ", "N")
        .replace("ñ", "n")
        .replace("Ò", "O")
        .replace("ò", "o")
        .replace("Ó", "O")
        .replace("ó", "o")
        .replace("Ô", "O")
        .replace("ô", "o")
        .replace("Õ", "O")
        .replace("õ", "o")
        .replace("Ö", "o")
        .replace("ö", "o")
        .replace("œ", "oe")
        .replace("Œ", "OE")
        .replace("Ø", "O")
        .replace("ø", "o")
        .replace("ß", "B")
        .replace("Ù", "U")
        .replace("ù", "u")
        .replace("Ú", "U")
        .replace("ú", "u")
        .replace("Û", "U")
        .replace("û", "u")
        .replace("Ü", "U")
        .replace("ü", "u")
        .replace("Ý", "Y")
        .replace("ý", "y")
        .replace("Þ", "P")
        .replace("þ", "P")
        .replace("Ÿ", "Y")
        .replace("ÿ", "y")
        .replace("%", "")
        # commas cause problems with shaka-packager resulting in decryption failure
        .replace(",", "")
        .replace(".mp4", "")
    )

    video_filepath_enc = lecture_file_name + ".encrypted.mp4"
    audio_filepath_enc = lecture_file_name + ".encrypted.m4a"
    video_filepath_dec = lecture_file_name + ".decrypted.mp4"
    audio_filepath_dec = lecture_file_name + ".decrypted.m4a"
    logger.info("> Downloading Lecture Tracks...")
    args = [
        "yt-dlp",
        "--enable-file-urls",
        "--force-generic-extractor",
        "--allow-unplayable-formats",
        "--concurrent-fragments",
        f"{concurrent_downloads}",
        "--downloader",
        "aria2c",
        "--fixup",
        "never",
        "-k",
        "-o",
        f"{lecture_file_name}.encrypted.%(ext)s",
        "-f",
        format_id,
        f"{url}",
    ]
    if disable_ipv6:
        args.append("--downloader-args")
        args.append('aria2c:"--disable-ipv6"')
    process = subprocess.Popen(args)
    log_subprocess_output("YTDLP-STDOUT", process.stdout)
    log_subprocess_output("YTDLP-STDERR", process.stderr)
    ret_code = process.wait()
    logger.info("> Lecture Tracks Downloaded")

    logger.debug("[-] Return code: " + str(ret_code))
    if ret_code != 0:
        logger.warning("[-] Return code from the downloader was non-0 (error), skipping!")
        return

    try:
        video_kid = extract_kid(video_filepath_enc)
        logger.info("KID for video file is: " + video_kid)
    except Exception:
        logger.exception(f"[-] Error extracting video kid")
        return

    try:
        audio_kid = extract_kid(audio_filepath_enc)
        logger.info("KID for audio file is: " + audio_kid)
    except Exception:
        logger.exception(f"[-] Error extracting audio kid")
        return

    try:
        logger.info("> Decrypting video, this might take a minute...")
        ret_code = decrypt(video_kid, video_filepath_enc, video_filepath_dec)
        if ret_code != 0:
            logger.error("> Return code from the decrypter was non-0 (error), skipping!")
            return
        logger.info("> Decryption complete")
        logger.info("> Decrypting audio, this might take a minute...")
        decrypt(audio_kid, audio_filepath_enc, audio_filepath_dec)
        if ret_code != 0:
            logger.error("> Return code from the decrypter was non-0 (error), skipping!")
            return
        logger.info("> Decryption complete")
        logger.info("> Merging video and audio, this might take a minute...")
        mux_process(video_title, video_filepath_dec, audio_filepath_dec, output_path)
        if ret_code != 0:
            logger.error("> Return code from ffmpeg was non-0 (error), skipping!")
            return
        logger.info("> Merging complete, removing temporary files...")
        os.remove(video_filepath_enc)
        os.remove(audio_filepath_enc)
        os.remove(video_filepath_dec)
        os.remove(audio_filepath_dec)
    except Exception:
        logger.exception(f"[-] Error: ")
    finally:
        os.chdir(HOME_DIR)
        # if the url is a file url, we need to remove the file after we're done with it
        if url.startswith("file://"):
            try:
                os.unlink(url[7:])
            except:
                pass


def check_for_aria():
    try:
        subprocess.Popen(["aria2c", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception("> Unexpected exception while checking for Aria2c, please tell the program author about this! ")
        return True


def check_for_ffmpeg():
    try:
        subprocess.Popen(["ffmpeg"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception("> Unexpected exception while checking for FFMPEG, please tell the program author about this! ")
        return True


def check_for_shaka():
    try:
        subprocess.Popen(["shaka-packager", "-version"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception("> Unexpected exception while checking for shaka-packager, please tell the program author about this! ")
        return True


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
    with (open(path, encoding="utf8", mode="ab")) as f:
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
    args = ["aria2c", url, "-o", filename, "-d", file_dir, "-j16", "-s20", "-x16", "-c", "--auto-file-renaming=false", "--summary-interval=0"]
    if disable_ipv6:
        args.append("--disable-ipv6")
    process = subprocess.Popen(args)
    log_subprocess_output("ARIA2-STDOUT", process.stdout)
    log_subprocess_output("ARIA2-STDERR", process.stderr)
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception("Return code from the downloader was non-0 (error)")
    return ret_code


def process_caption(caption, lecture_title, lecture_dir, tries=0):
    filename = f"%s_%s.%s" % (sanitize_filename(lecture_title), caption.get("language"), caption.get("extension"))
    filename_no_ext = f"%s_%s" % (sanitize_filename(lecture_title), caption.get("language"))
    filepath = os.path.join(lecture_dir, filename)

    if os.path.isfile(filepath):
        logger.info("    > Caption '%s' already downloaded." % filename)
    else:
        logger.info(f"    >  Downloading caption: '%s'" % filename)
        try:
            ret_code = download_aria(caption.get("download_url"), lecture_dir, filename)
            logger.debug(f"      > Download return code: {ret_code}")
        except Exception as e:
            if tries >= 3:
                logger.error(f"    > Error downloading caption: {e}. Exceeded retries, skipping.")
                return
            else:
                logger.error(f"    > Error downloading caption: {e}. Will retry {3-tries} more times.")
                process_caption(caption, lecture_title, lecture_dir, tries + 1)
        if caption.get("extension") == "vtt":
            try:
                logger.info("    > Converting caption to SRT format...")
                convert(lecture_dir, filename_no_ext)
                logger.info("    > Caption conversion complete.")
                if not keep_vtt:
                    os.remove(filepath)
            except Exception:
                logger.exception(f"    > Error converting caption")


def process_lecture(lecture, lecture_path, lecture_file_name, chapter_dir):
    lecture_title = lecture.get("lecture_title")
    is_encrypted = lecture.get("is_encrypted")
    lecture_sources = lecture.get("video_sources")

    if is_encrypted:
        if len(lecture_sources) > 0:
            source = lecture_sources[-1]  # last index is the best quality
            if isinstance(quality, int):
                source = min(lecture_sources, key=lambda x: abs(int(x.get("height")) - quality))
            logger.info(f"      > Lecture '%s' has DRM, attempting to download" % lecture_title)
            handle_segments(source.get("download_url"), source.get("format_id"), lecture_title, lecture_path, lecture_file_name, chapter_dir)
        else:
            logger.info(f"      > Lecture '%s' is missing media links" % lecture_title)
            logger.debug(f"Lecture source count: {len(lecture_sources)}")
    else:
        sources = lecture.get("sources")
        sources = sorted(sources, key=lambda x: int(x.get("height")), reverse=True)
        if sources:
            if not os.path.isfile(lecture_path):
                logger.info("      > Lecture doesn't have DRM, attempting to download...")
                source = sources[0]  # first index is the best quality
                if isinstance(quality, int):
                    source = min(sources, key=lambda x: abs(int(x.get("height")) - quality))
                try:
                    logger.info("      ====== Selected quality: %s %s", source.get("type"), source.get("height"))
                    url = source.get("download_url")
                    source_type = source.get("type")
                    if source_type == "hls":
                        temp_filepath = lecture_path.replace(".mp4", ".%(ext)s")
                        cmd = [
                            "yt-dlp",
                            "--enable-file-urls",
                            "--force-generic-extractor",
                            "--concurrent-fragments",
                            f"{concurrent_downloads}",
                            "--downloader",
                            "aria2c",
                            "-o",
                            f"{temp_filepath}",
                            f"{url}",
                        ]
                        if disable_ipv6:
                            cmd.append("--downloader-args")
                            cmd.append('aria2c:"--disable-ipv6"')
                        process = subprocess.Popen(cmd)
                        log_subprocess_output("YTDLP-STDOUT", process.stdout)
                        log_subprocess_output("YTDLP-STDERR", process.stderr)
                        ret_code = process.wait()
                        if ret_code == 0:
                            tmp_file_path = lecture_path + ".tmp"
                            logger.info("      > HLS Download success")
                            if use_h265:
                                codec = "hevc_nvenc" if use_nvenc else "libx265"
                                transcode = "-hwaccel cuda -hwaccel_output_format cuda".split(" ") if use_nvenc else []
                                cmd = ["ffmpeg", *transcode, "-y", "-i", lecture_path, "-c:v", codec, "-c:a", "copy", "-f", "mp4", tmp_file_path]
                                process = subprocess.Popen(cmd)
                                log_subprocess_output("FFMPEG-STDOUT", process.stdout)
                                log_subprocess_output("FFMPEG-STDERR", process.stderr)
                                ret_code = process.wait()
                                if ret_code == 0:
                                    os.unlink(lecture_path)
                                    os.rename(tmp_file_path, lecture_path)
                                    logger.info("      > Encoding complete")
                                else:
                                    logger.error("      > Encoding returned non-zero return code")
                    else:
                        ret_code = download_aria(url, chapter_dir, lecture_title + ".mp4")
                        logger.debug(f"      > Download return code: {ret_code}")
                except Exception:
                    logger.exception(f">        Error downloading lecture")
            else:
                logger.info(f"      > Lecture '{lecture_title}' is already downloaded, skipping...")
        else:
            logger.error("      > Missing sources for lecture", lecture)


def parse_new(udemy: Udemy, udemy_object: dict):
    total_chapters = udemy_object.get("total_chapters")
    total_lectures = udemy_object.get("total_lectures")
    logger.info(f"Chapter(s) ({total_chapters})")
    logger.info(f"Lecture(s) ({total_lectures})")

    course_name = str(udemy_object.get("course_id")) if id_as_course_name else udemy_object.get("course_title")
    course_dir = os.path.join(DOWNLOAD_DIR, course_name)
    if not os.path.exists(course_dir):
        os.mkdir(course_dir)

    for chapter in udemy_object.get("chapters"):
        chapter_title = chapter.get("chapter_title")
        chapter_index = chapter.get("chapter_index")
        chapter_dir = os.path.join(course_dir, chapter_title)
        if not os.path.exists(chapter_dir):
            os.mkdir(chapter_dir)
        logger.info(f"======= Processing chapter {chapter_index} of {total_chapters} =======")

        for lecture in chapter.get("lectures"):
            index = lecture.get("index")  # this is lecture_counter
            lecture_index = lecture.get("lecture_index")  # this is the raw object index from udemy
            lecture_title = lecture.get("lecture_title")
            
            parsed_lecture = udemy._parse_lecture(lecture)

            lecture_extension = parsed_lecture.get("extension")
            extension = "mp4"  # video lectures dont have an extension property, so we assume its mp4
            if lecture_extension != None:
                # if the lecture extension property isnt none, set the extension to the lecture extension
                extension = lecture_extension
            lecture_file_name = sanitize_filename(lecture_title + "." + extension)
            lecture_path = os.path.join(chapter_dir, lecture_file_name)

            logger.info(f"  > Processing lecture {lecture_index} of {total_lectures}")
            if not skip_lectures:
                # Check if the lecture is already downloaded
                if os.path.isfile(lecture_path):
                    logger.info("      > Lecture '%s' is already downloaded, skipping..." % lecture_title)
                else:
                    # Check if the file is an html file
                    if extension == "html":
                        # if the html content is None or an empty string, skip it so we dont save empty html files
                        if parsed_lecture.get("html_content") != None and parsed_lecture.get("html_content") != "":
                            html_content = parsed_lecture.get("html_content").encode("ascii", "ignore").decode("utf8")
                            lecture_path = os.path.join(chapter_dir, "{}.html".format(sanitize_filename(lecture_title)))
                            try:
                                with open(lecture_path, encoding="utf8", mode="w") as f:
                                    f.write(html_content)
                                    f.close()
                            except Exception:
                                logger.exception("    > Failed to write html file")
                    else:
                        process_lecture(parsed_lecture, lecture_path, lecture_file_name, chapter_dir)

            # download subtitles for this lecture
            subtitles = parsed_lecture.get("subtitles")
            if dl_captions and subtitles != None and lecture_extension == None:
                logger.info("Processing {} caption(s)...".format(len(subtitles)))
                for subtitle in subtitles:
                    lang = subtitle.get("language")
                    if lang == caption_locale or caption_locale == "all":
                        process_caption(subtitle, lecture_title, chapter_dir)

            if dl_assets:
                assets = parsed_lecture.get("assets")
                logger.info("    > Processing {} asset(s) for lecture...".format(len(assets)))

                for asset in assets:
                    asset_type = asset.get("type")
                    filename = asset.get("filename")
                    download_url = asset.get("download_url")

                    if asset_type == "article":
                        logger.warning(
                            "If you're seeing this message, that means that you reached a secret area that I haven't finished! jk I haven't implemented handling for this asset type, please report this at https://github.com/Puyodead1/udemy-downloader/issues so I can add it. When reporting, please provide the following information: "
                        )
                        logger.warning("AssetType: Article; AssetData: ", asset)
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
                        logger.warning(
                            "If you're seeing this message, that means that you reached a secret area that I haven't finished! jk I haven't implemented handling for this asset type, please report this at https://github.com/Puyodead1/udemy-downloader/issues so I can add it. When reporting, please provide the following information: "
                        )
                        logger.warning("AssetType: Video; AssetData: ", asset)
                    elif asset_type == "audio" or asset_type == "e-book" or asset_type == "file" or asset_type == "presentation" or asset_type == "ebook":
                        try:
                            ret_code = download_aria(download_url, chapter_dir, filename)
                            logger.debug(f"      > Download return code: {ret_code}")
                        except Exception:
                            logger.exception("> Error downloading asset")
                    elif asset_type == "external_link":
                        # write the external link to a shortcut file
                        file_path = os.path.join(chapter_dir, f"{filename}.url")
                        file = open(file_path, "w")
                        file.write("[InternetShortcut]\n")
                        file.write(f"URL={download_url}")
                        file.close()

                        # save all the external links to a single file
                        savedirs, name = os.path.split(os.path.join(chapter_dir, filename))
                        filename = "external-links.txt"
                        filename = os.path.join(savedirs, filename)
                        file_data = []
                        if os.path.isfile(filename):
                            file_data = [i.strip().lower() for i in open(filename, encoding="utf-8", errors="ignore") if i]

                        content = "\n{}\n{}\n".format(name, download_url)
                        if name.lower() not in file_data:
                            with open(filename, "a", encoding="utf-8", errors="ignore") as f:
                                f.write(content)
                                f.close()


def _print_course_info(udemy: Udemy, udemy_object: dict):
    course_title = udemy_object.get("title")
    chapter_count = udemy_object.get("total_chapters")
    lecture_count = udemy_object.get("total_lectures")

    logger.info("> Course: {}".format(course_title))
    logger.info("> Total Chapters: {}".format(chapter_count))
    logger.info("> Total Lectures: {}".format(lecture_count))
    logger.info("\n")

    chapters = udemy_object.get("chapters")
    for chapter in chapters:
        chapter_title = chapter.get("chapter_title")
        chapter_index = chapter.get("chapter_index")
        chapter_lecture_count = chapter.get("lecture_count")
        chapter_lectures = chapter.get("lectures")

        logger.info("> Chapter: {} ({} of {})".format(chapter_title, chapter_index, chapter_count))

        for lecture in chapter_lectures:
            lecture_index = lecture.get("lecture_index")  # this is the raw object index from udemy
            lecture_title = lecture.get("lecture_title")
            parsed_lecture = udemy._parse_lecture(lecture)

            lecture_sources = parsed_lecture.get("sources")
            lecture_is_encrypted = parsed_lecture.get("is_encrypted")
            lecture_extension = parsed_lecture.get("extension")
            lecture_asset_count = parsed_lecture.get("assets_count")
            lecture_subtitles = parsed_lecture.get("subtitles")
            lecture_video_sources = parsed_lecture.get("video_sources")

            if lecture_sources:
                lecture_sources = sorted(lecture_sources, key=lambda x: int(x.get("height")), reverse=True)
            if lecture_video_sources:
                lecture_video_sources = sorted(lecture_video_sources, key=lambda x: int(x.get("height")), reverse=True)

            if lecture_is_encrypted:
                lecture_qualities = ["{}@{}x{}".format(x.get("type"), x.get("width"), x.get("height")) for x in lecture_video_sources]
            elif not lecture_is_encrypted and lecture_sources:
                lecture_qualities = ["{}@{}x{}".format(x.get("type"), x.get("height"), x.get("width")) for x in lecture_sources]

            if lecture_extension:
                continue

            logger.info("  > Lecture: {} ({} of {})".format(lecture_title, lecture_index, chapter_lecture_count))
            logger.info("    > DRM: {}".format(lecture_is_encrypted))
            logger.info("    > Asset Count: {}".format(lecture_asset_count))
            logger.info("    > Captions: {}".format(", ".join([x.get("language") for x in lecture_subtitles])))
            logger.info("    > Qualities: {}".format(lecture_qualities))

        if chapter_index != chapter_count:
            logger.info("==========================================")


def main():
    global bearer_token, selenium

    aria_ret_val = check_for_aria()
    if not aria_ret_val:
        logger.fatal("> Aria2c is missing from your system or path!")
        sys.exit(1)

    ffmpeg_ret_val = check_for_ffmpeg()
    if not ffmpeg_ret_val and not skip_lectures:
        logger.fatal("> FFMPEG is missing from your system or path!")
        sys.exit(1)

    shaka_ret_val = check_for_shaka()
    if not shaka_ret_val and not skip_lectures:
        logger.fatal("> Shaka Packager is missing from your system or path!")
        sys.exit(1)

    if load_from_file:
        logger.info("> 'load_from_file' was specified, data will be loaded from json files instead of fetched")
    if save_to_file:
        logger.info("> 'save_to_file' was specified, data will be saved to json files")

    udemy = Udemy(bearer_token)
    if is_subscription_course:
        selenium = Selenium()

    if not load_from_file:
        if is_subscription_course:
            logger.info("> Fetching course information as a subscription course, this may take a minute...")
            course_id, course_info = udemy._extract_course_info_sub(selenium, course_url)
        else:
            logger.info("> Fetching course information, this may take a minute...")
            course_id, course_info = udemy._extract_course_info(course_url)
            
        logger.info("> Course information retrieved!")
        if course_info and isinstance(course_info, dict):
            title = sanitize_filename(course_info.get("title"))
            course_title = course_info.get("published_title")
            portal_name = course_info.get("portal_name")

        logger.info("> Fetching course content, this may take a minute...")
        if is_subscription_course:
            # add some delay before switching pages to try and avoid captchas
            delay = random.randint(1, 5)
            time.sleep(delay)
            course_json = udemy._extract_course_json_sub(selenium, course_id, portal_name)
        else:
            course_json = udemy._extract_course_json(course_url, course_id, portal_name)

    else:
        logger.info("> Loading cached course content, this may take a minute...")
        course_json = json.loads(open(os.path.join(os.getcwd(), "saved", "course_content.json"), encoding="utf8", mode="r").read())
        title = course_json.get("title")
        course_title = course_json.get("published_title")
        portal_name = course_json.get("portal_name")

    # close selenium if it's running
    if selenium:
        selenium.driver.quit()

    if save_to_file:
        with open(os.path.join(os.getcwd(), "saved", "course_content.json"), encoding="utf8", mode="w") as f:
            f.write(json.dumps(course_json))
            f.close()

    logger.info("> Course content retrieved!")
    course = course_json.get("results")
    resource = course_json.get("detail")

    if load_from_file:
        udemy_object = json.loads(open(os.path.join(os.getcwd(), "saved", "_udemy.json"), encoding="utf8", mode="r").read())
        if info:
            _print_course_info(udemy, udemy_object)
        else:
            parse_new(udemy, udemy_object)
    else:
        udemy_object = {}
        udemy_object["bearer_token"] = bearer_token
        udemy_object["course_id"] = course_id
        udemy_object["title"] = title
        udemy_object["course_title"] = course_title
        udemy_object["chapters"] = []
        counter = -1

        if resource:
            logger.info("> Trying to logout")
            udemy.session.terminate()
            logger.info("> Logged out.")

        if course:
            logger.info("> Processing course data, this may take a minute. ")
            lecture_counter = 0
            for entry in course:
                clazz = entry.get("_class")

                if clazz == "chapter":
                    lecture_counter = 0
                    lectures = []
                    chapter_index = entry.get("object_index")
                    chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))

                    if chapter_title not in udemy_object["chapters"]:
                        udemy_object["chapters"].append({"chapter_title": chapter_title, "chapter_id": entry.get("id"), "chapter_index": chapter_index, "lectures": []})
                        counter += 1
                elif clazz == "lecture":
                    lecture_counter += 1
                    lecture_id = entry.get("id")
                    if len(udemy_object["chapters"]) == 0:
                        lectures = []
                        chapter_index = entry.get("object_index")
                        chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))
                        if chapter_title not in udemy_object["chapters"]:
                            udemy_object["chapters"].append({"chapter_title": chapter_title, "chapter_id": lecture_id, "chapter_index": chapter_index, "lectures": []})
                            counter += 1

                    if lecture_id:
                        logger.info(f"Processing {course.index(entry)} of {len(course)}")

                        lecture_index = entry.get("object_index")
                        lecture_title = "{0:03d} ".format(lecture_counter) + sanitize_filename(entry.get("title"))

                        lectures.append({"index": lecture_counter, "lecture_index": lecture_index, "lecture_title": lecture_title, "data": entry})
                    udemy_object["chapters"][counter]["lectures"] = lectures
                    udemy_object["chapters"][counter]["lecture_count"] = len(lectures)
                elif clazz == "quiz":
                    lecture_id = entry.get("id")
                    if len(udemy_object["chapters"]) == 0:
                        lectures = []
                        chapter_index = entry.get("object_index")
                        chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))
                        if chapter_title not in udemy_object["chapters"]:
                            lecture_counter = 0
                            udemy_object["chapters"].append(
                                {
                                    "chapter_title": chapter_title,
                                    "chapter_id": lecture_id,
                                    "chapter_index": chapter_index,
                                    "lectures": [],
                                }
                            )
                            counter += 1

                    udemy_object["chapters"][counter]["lectures"] = lectures
                    udemy_object["chapters"][counter]["lectures_count"] = len(lectures)

            udemy_object["total_chapters"] = len(udemy_object["chapters"])
            udemy_object["total_lectures"] = sum([entry.get("lecture_count", 0) for entry in udemy_object["chapters"] if entry])

        if save_to_file:
            with open(os.path.join(os.getcwd(), "saved", "_udemy.json"), encoding="utf8", mode="w") as f:
                # remove "bearer_token" from the object before writing
                udemy_object.pop("bearer_token")
                f.write(json.dumps(udemy_object))
                f.close()
            logger.info("> Saved parsed data to json")

        if info:
            _print_course_info(udemy, udemy_object)
        else:
            parse_new(udemy, udemy_object)


if __name__ == "__main__":
    # pre run parses arguments, sets up logging, and creates directories
    pre_run()
    # run main program
    main()
