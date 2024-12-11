import json
import logging
import math
import os
import re
import subprocess
import sys
import time
from http.cookiejar import CookieJar, MozillaCookieJar
from pathlib import Path
from typing import Union

import browser_cookie3
import m3u8
import yt_dlp
from bs4 import BeautifulSoup
from coloredlogs import ColoredFormatter
from pathvalidate import sanitize_filename

from udemy_downloader.constants import (
    COLLECTION_URL,
    COURSE_SEARCH,
    COURSE_URL,
    CURRICULUM_ITEMS_PARAMS,
    CURRICULUM_ITEMS_URL,
    LOGGER_NAME,
    MY_COURSES_URL,
    QUIZ_URL,
)
from udemy_downloader.Session import Session
from udemy_downloader.UdemyAuth import UdemyAuth
from udemy_downloader.utils import (
    check_for_aria,
    check_for_ffmpeg,
    deEmojify,
    download_aria,
    extract_kid,
    log_subprocess_output,
    parse_chapter_filter
)
from udemy_downloader.vtt_to_srt import convert


class Udemy:
    def __init__(
        self,
        bearer_token: Union[str, None],
        browser: Union[str, None],
        is_subscription_course: bool,
        skip_hls: bool,
        download_assets: bool,
        lang: Union[str, None],
        download_captions: bool,
        download_quizzes: bool,
        skip_lectures: bool,
        quality: Union[str, None],
        keep_vtt: bool,
        concurrent_downloads: int,
        load_from_file: bool,
        save_to_file: bool,
        course_url: str,
        info: bool,
        use_h265: bool,
        h265_crf: int,
        h265_preset: str,
        use_nvenc: bool,
        log_level_str: str,
        id_as_course_name: bool,
        out: str,
        use_continuous_lecture_numbers: bool,
        chapter_filter_raw: Union[str, None] = None,
    ):
        self.keys: dict[str, str] = {}
        self.session: Union[Session, None] = None
        self.cj: CookieJar = None
        self.logger: logging.Logger
        self.auth = UdemyAuth()
        self.parsed_data = {}

        self.bearer_token = bearer_token
        self.browser = browser
        self.is_subscription_course = is_subscription_course
        self.skip_hls = skip_hls
        self.download_assets = download_assets
        self.lang = lang
        self.download_captions = download_captions
        self.download_quizzes = download_quizzes
        self.skip_lectures = skip_lectures
        self.quality = quality
        self.keep_vtt = keep_vtt
        self.concurrent_downloads = concurrent_downloads
        self.load_from_file = load_from_file
        self.save_to_file = save_to_file
        self.course_url = course_url
        self.info = info
        self.use_h265 = use_h265
        self.h265_crf = h265_crf
        self.h265_preset = h265_preset
        self.use_nvenc = use_nvenc
        self.log_level_str = log_level_str
        self.id_as_course_name = id_as_course_name
        self.out = out
        self.use_continuous_lecture_numbers = use_continuous_lecture_numbers
        
        # Process the chapter filter
        if chapter_filter_raw:
            self.chapter_filter = parse_chapter_filter(chapter_filter_raw)
            self.logger.info("Chapter filter applied: %s", sorted(self.chapter_filter))

        self.home_dir = Path(os.getcwd())
        self.download_dir = self.home_dir / "downloads"
        self.saved_dir = self.home_dir / "saved"
        self.key_file_path = self.home_dir / "keyfile.json"
        self.cookies_path = self.home_dir / "cookies.txt"
        self.log_dir = self.home_dir / "logs"
        self.log_file_path = self.log_dir / f"{time.strftime('%Y-%m-%d-%I-%M-%S')}.log"
        self.log_format = "[%(asctime)s] [%(name)s] [%(funcName)s:%(lineno)d] %(levelname)s: %(message)s"
        self.log_date_format = "%I:%M:%S"

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.saved_dir.mkdir(parents=True, exist_ok=True)

    def init_logger(self):
        # parse the log level string to a log level
        self.log_level = getattr(logging, self.log_level_str.upper(), logging.INFO)

        # create a colored formatter for the console
        console_formatter = ColoredFormatter(self.log_format, datefmt=self.log_date_format)
        # create a regular non-colored formatter for the log file
        file_formatter = logging.Formatter(self.log_format, datefmt=self.log_date_format)

        # create a handler for console logging
        stream = logging.StreamHandler()
        stream.setLevel(self.log_level)
        stream.setFormatter(console_formatter)

        # create a handler for file logging
        file_handler = logging.FileHandler(self.log_file_path)
        file_handler.setFormatter(file_formatter)

        # construct the logger
        self.logger = logging.getLogger(LOGGER_NAME)
        self.logger.setLevel(self.log_level)
        self.logger.addHandler(stream)
        self.logger.addHandler(file_handler)

    def pre_check(self):
        is_aria_installed = check_for_aria()
        is_ffmpeg_installed, ffmpeg_version = check_for_ffmpeg()

        if not is_aria_installed:
            self.logger.fatal("> Failed to find Aria2c!")
            sys.exit(1)

        if not is_ffmpeg_installed:
            self.logger.fatal("> Failed to find FFmpeg!")
            sys.exit(1)

        # ffmpeg version check, 5.0+ is required
        match = re.search(r"ffmpeg version (\d+)\.(\d+)", ffmpeg_version)
        if match:
            major_version = int(match.group(1))  # major version
            minor_version = int(match.group(2))  # minor version
            if major_version >= 5:
                self.logger.info(f"Found FFmpeg version {major_version}.{minor_version}")
            else:
                self.logger.info(
                    f"FFmpeg version {major_version}.{minor_version} is too old! Please update to version 5 or higher."
                )
        else:
            self.logger.warning("Failed to extract FFmpeg version.")

    def update_auth(self):
        if not self.session:
            self.session = self.auth.update_token(self.bearer_token)

        # if the session is still None, use cookie auth
        if not self.session:
            if self.browser == None:
                self.logger.error("No bearer token was provided, and no browser for cookie extraction was specified.")
                sys.exit(1)

            self.logger.warning("No bearer token was provided, attempting to use browser cookies.")

            self.session = self.auth._session

            if self.browser == "chrome":
                self.cj = browser_cookie3.chrome()
            elif self.browser == "firefox":
                self.cj = browser_cookie3.firefox()
            elif self.browser == "opera":
                self.cj = browser_cookie3.opera()
            elif self.browser == "edge":
                self.cj = browser_cookie3.edge()
            elif self.browser == "brave":
                self.cj = browser_cookie3.brave()
            elif self.browser == "chromium":
                self.cj = browser_cookie3.chromium()
            elif self.browser == "vivaldi":
                self.cj = browser_cookie3.vivaldi()
            elif self.browser == "file":
                # load netscape cookies from file
                self.cj = MozillaCookieJar("cookies.txt")
                self.cj.load()

            self.session.set_cookiejar(self.cj)

    def get_course_info(self):
        self.logger.info("> Fetching course information, this may take a minute...")
        if not self.load_from_file:
            course_id, portal_name, course_info = self.extract_course_info(self.course_url)
            self.course_id = course_id
            self.portal_name = portal_name
            if course_info and isinstance(course_info, dict):
                self.course_title = sanitize_filename(course_info.get("title"))
                self.course_slug = course_info.get("published_title")
                self.logger.info(f"> Successfully fetched course '{self.course_title}'")

    def get_course_content(self):
        self.logger.info("> Fetching course content, this may take a minute...")
        if self.load_from_file:
            self.load_content_file()
        else:
            self.course_data = self.extract_course_content(self.portal_name, self.course_id, self.course_url)
            self.course_data["portal_name"] = self.portal_name

        chapter_count = len([x for x in self.course_data["results"] if x["_class"] == "chapter"])
        lecture_count = len([x for x in self.course_data["results"] if x["_class"] == "lecture"])

        self.logger.info(
            f"> Successfully fetched {chapter_count} chapters and {lecture_count} lectures for '{self.course_title}'"
        )

    def save_content_file(self):
        course_data = self.course_data.copy()
        course_data["course_id"] = self.course_id
        course_data["course_title"] = self.course_title
        course_data["course_slug"] = self.course_slug
        course_data["portal_name"] = self.portal_name

        with (self.saved_dir / "course_content.json").open(mode="w", encoding="utf8") as f:
            f.write(json.dumps(course_data))

    def load_content_file(self):
        self.course_data = json.loads((self.saved_dir / "course_content.json").open(mode="r", encoding="utf8").read())

        self.course_id = self.course_data.get("course_id")
        self.portal_name = self.course_data.get("portal_name")
        self.course_title = self.course_data.get("course_title")
        self.course_slug = self.course_data.get("course_slug")

    def save_parsed_file(self):
        # create a clone
        parsed_data = self.parsed_data.copy()
        # remove the bearer token
        parsed_data.pop("bearer_token")

        with (self.saved_dir / "_udemy.json").open(mode="w", encoding="utf8") as f:
            f.write(json.dumps(parsed_data))

    def load_parsed_file(self):
        self.parsed_data = json.loads((self.saved_dir / "_udemy.json").open(mode="r", encoding="utf8").read())
        self.course_id = self.parsed_data.get("course_id")
        self.portal_name = self.parsed_data.get("portal_name")
        self.course_title = self.parsed_data.get("course_title")

    def _get_quiz(self, quiz_id: str):
        self.session._headers.update(
            {
                "Host": "{portal_name}.udemy.com".format(portal_name=self.portal_name),
                "Referer": "https://{portal_name}.udemy.com/course/{course_name}/learn/quiz/{quiz_id}".format(
                    portal_name=self.portal_name, course_name=self.course_name, quiz_id=quiz_id
                ),
            }
        )
        url = QUIZ_URL.format(portal_name=self.portal_name, quiz_id=quiz_id)
        try:
            resp = self.session._get(url).json()
        except ConnectionError as error:
            self.logger.fatal(f"[-] Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            return resp.get("results")

    def _get_elem_value_or_none(self, elem, key):
        return elem[key] if elem and key in elem else "(None)"

    def _get_quiz_with_info(self, quiz_id: str):
        resp = {"_class": None, "_type": None, "contents": None}
        quiz_json = self._get_quiz(quiz_id)
        is_only_one = len(quiz_json) == 1 and quiz_json[0]["_class"] == "assessment"
        is_coding_assignment = quiz_json[0]["assessment_type"] == "coding-problem"

        resp["_class"] = quiz_json[0]["_class"]

        if is_only_one and is_coding_assignment:
            assignment = quiz_json[0]
            prompt = assignment["prompt"]

            resp["_type"] = assignment["assessment_type"]

            resp["contents"] = {
                "instructions": self._get_elem_value_or_none(prompt, "instructions"),
                "tests": self._get_elem_value_or_none(prompt, "test_files"),
                "solutions": self._get_elem_value_or_none(prompt, "solution_files"),
            }

            resp["hasInstructions"] = False if resp["contents"]["instructions"] == "(None)" else True
            resp["hasTests"] = False if isinstance(resp["contents"]["tests"], str) else True
            resp["hasSolutions"] = False if isinstance(resp["contents"]["solutions"], str) else True
        else:  # Normal quiz
            resp["_type"] = "normal-quiz"
            resp["contents"] = quiz_json

        return resp

    def _extract_supplementary_assets(self, supp_assets: list, lecture_counter: int):
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
                    _temp.append(
                        {
                            "type": "file",
                            "title": title,
                            "filename": "{0:03d} ".format(lecture_counter) + filename,
                            "extension": extension,
                            "download_url": download_url,
                            "id": id,
                        }
                    )
            elif asset_type == "sourcecode":
                if download_urls and isinstance(download_urls, dict):
                    extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
                    download_url = download_urls.get("SourceCode", [])[0].get("file")
                    _temp.append(
                        {
                            "type": "source_code",
                            "title": title,
                            "filename": "{0:03d} ".format(lecture_counter) + filename,
                            "extension": extension,
                            "download_url": download_url,
                            "id": id,
                        }
                    )
            elif asset_type == "externallink":
                _temp.append(
                    {
                        "type": "external_link",
                        "title": title,
                        "filename": "{0:03d} ".format(lecture_counter) + filename,
                        "extension": "txt",
                        "download_url": external_url,
                        "id": id,
                    }
                )
        return _temp

    def _extract_article(self, asset: dict, id: str):
        return [
            {
                "type": "article",
                "body": asset.get("body"),
                "extension": "html",
                "id": id,
            }
        ]

    def _extract_ppt(self, asset: dict, lecture_counter: int):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("Presentation", [])[0].get("file")
            _temp.append(
                {
                    "type": "presentation",
                    "filename": "{0:03d} ".format(lecture_counter) + filename,
                    "extension": extension,
                    "download_url": download_url,
                    "id": id,
                }
            )
        return _temp

    def _extract_file(self, asset: dict, lecture_counter: int):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("File", [])[0].get("file")
            _temp.append(
                {
                    "type": "file",
                    "filename": "{0:03d} ".format(lecture_counter) + filename,
                    "extension": extension,
                    "download_url": download_url,
                    "id": id,
                }
            )
        return _temp

    def _extract_ebook(self, asset: dict, lecture_counter: int):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("E-Book", [])[0].get("file")
            _temp.append(
                {
                    "type": "ebook",
                    "filename": "{0:03d} ".format(lecture_counter) + filename,
                    "extension": extension,
                    "download_url": download_url,
                    "id": id,
                }
            )
        return _temp

    def _extract_audio(self, asset: dict, lecture_counter: int):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("Audio", [])[0].get("file")
            _temp.append(
                {
                    "type": "audio",
                    "filename": "{0:03d} ".format(lecture_counter) + filename,
                    "extension": extension,
                    "download_url": download_url,
                    "id": id,
                }
            )
        return _temp

    def _extract_sources(self, sources, skip_hls: bool):
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

    def _extract_media_sources(self, sources: list):
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
                lang = (
                    track.get("language")
                    or track.get("srclang")
                    or track.get("label")
                    or track["locale_id"].split("_")[0]
                )
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

    def _extract_m3u8(self, url: str):
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
            self.logger.error(f"Udemy Says : '{error}' while fetching hls streams..")
        return _temp

    def _extract_mpd(self, url):
        """extracts mpd streams"""
        asset_id_re = re.compile(r"assets/(?P<id>\d+)/")
        _temp = {}

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

            ytdl = yt_dlp.YoutubeDL(
                {"quiet": True, "no_warnings": True, "allow_unplayable_formats": True, "enable_file_urls": True}
            )
            results = ytdl.extract_info(mpd_path.as_uri(), download=False, force_generic_extractor=True)
            formats = results.get("formats", [])
            best_audio = next(f for f in formats if (f["acodec"] != "none" and f["vcodec"] == "none"))
            # filter formats to remove any audio only formats
            formats = [f for f in formats if f["vcodec"] != "none" and f["acodec"] == "none"]
            if not best_audio:
                raise ValueError("No suitable audio format found in MPD")
            audio_format_id = best_audio.get("format_id")

            for format in formats:
                video_format_id = format.get("format_id")
                extension = format.get("ext")
                height = format.get("height")
                width = format.get("width")
                tbr = format.get("tbr", 0)

                # add to dict based on height
                if height not in _temp:
                    _temp[height] = []

                _temp[height].append(
                    {
                        "type": "dash",
                        "height": str(height),
                        "width": str(width),
                        "format_id": f"{video_format_id},{audio_format_id}",
                        "extension": extension,
                        "download_url": mpd_path.as_uri(),
                        "tbr": round(tbr),
                    }
                )
            # for each resolution, use only the highest bitrate
            _temp2 = []
            for height, formats in _temp.items():
                if formats:
                    # sort by tbr and take the first one
                    formats.sort(key=lambda x: x["tbr"], reverse=True)
                    _temp2.append(formats[0])
                else:
                    del _temp[height]

            _temp = _temp2
        except Exception:
            logger.exception(f"Error fetching MPD streams")

        # We don't delete the mpd file yet because we can use it to download later
        return _temp

    def extract_course_name(self, url: str):
        """
        @author r0oth3x49
        """
        obj = re.search(
            r"(?i)(?://(?P<portal_name>.+?).udemy.com/(?:course(/draft)*/)?(?P<name_or_id>[a-zA-Z0-9_-]+))",
            url,
        )
        if obj:
            return obj.group("portal_name"), obj.group("name_or_id")

    def extract_portal_name(self, url: str):
        obj = re.search(r"(?i)(?://(?P<portal_name>.+?).udemy.com)", url)
        if obj:
            return obj.group("portal_name")

    def _subscribed_courses(self, portal_name: str, course_name: str):
        results = []
        self.session._headers.update(
            {
                "Host": "{portal_name}.udemy.com".format(portal_name=portal_name),
                "Referer": "https://{portal_name}.udemy.com/home/my-courses/search/?q={course_name}".format(
                    portal_name=portal_name, course_name=course_name
                ),
            }
        )
        url = COURSE_SEARCH.format(portal_name=portal_name, course_name=course_name)
        try:
            webpage = self.session._get(url).content
            webpage = webpage.decode("utf8", "ignore")
            webpage = json.loads(webpage)
        except ConnectionError as error:
            self.logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            self.logger.fatal(f"{error} on {url}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
        return results

    def _extract_course_info_json(self, portal_name: str, course_id: str, url: str):
        self.session._headers.update({"Referer": url})
        url = COURSE_URL.format(portal_name=portal_name, course_id=course_id)
        try:
            resp = self.session._get(url).json()
        except ConnectionError as error:
            self.logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            return resp

    def extract_course_content(self, portal_name: str, course_id: str, url: str):
        self.session._headers.update({"Referer": url})
        url = CURRICULUM_ITEMS_URL.format(portal_name=portal_name, course_id=course_id)
        page = 1
        try:
            data = self.session._get(url, CURRICULUM_ITEMS_PARAMS).json()
        except ConnectionError as error:
            self.logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            _next = data.get("next")
            _count = data.get("count")
            est_page_count = math.ceil(_count / 100)  # 100 is the max results per page
            while _next:
                self.logger.info(f"> Downloading course curriculum.. (Page {page + 1}/{est_page_count})")
                try:
                    resp = self.session._get(_next)
                    if not resp.ok:
                        self.logger.error(f"Failed to fetch a page, will retry")
                        continue
                    resp = resp.json()
                except ConnectionError as error:
                    self.logger.fatal(f"Connection error: {error}")
                    time.sleep(0.8)
                    sys.exit(1)
                else:
                    _next = resp.get("next")
                    results = resp.get("results")
                    if results and isinstance(results, list):
                        for d in resp["results"]:
                            data["results"].append(d)
                        page = page + 1
            return data

    def _extract_course(self, response, course_name: str):
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
        except ConnectionError as error:
            self.logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            self.logger.fatal(f"{error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
        return results

    def _subscribed_collection_courses(self, portal_name: str):
        url = COLLECTION_URL.format(portal_name=portal_name)
        courses_lists = []
        try:
            webpage = self.session._get(url).json()
        except ConnectionError as error:
            self.logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            self.logger.fatal(f"{error}")
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
        except ConnectionError as error:
            self.logger.fatal(f"Connection error: {error}")
            time.sleep(0.8)
            sys.exit(1)
        except (ValueError, Exception) as error:
            self.logger.fatal(f"{error}")
            time.sleep(0.8)
            sys.exit(1)
        else:
            results = webpage.get("results", [])
        return results

    def _extract_subscription_course_info(self, url):
        course_html = self.session._get(url).text
        soup = BeautifulSoup(course_html, "lxml")
        data = soup.find("div", {"class": "ud-component--course-taking--app"})
        if not data:
            self.logger.fatal(
                "Could not find course data. Possible causes are: Missing cookies.txt file, incorrect url (should end with /learn), not logged in to udemy in specified browser."
            )
            self.session.terminate()
            sys.exit(1)
        data_args = data.attrs["data-module-args"]
        data_json = json.loads(data_args)
        course_id = data_json.get("courseId", None)
        return course_id

    def extract_course_info(self, url: str):
        portal_name, course_name = self.extract_course_name(url)
        course = {"portal_name": portal_name}

        if not self.is_subscription_course:
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

        if not course or self.is_subscription_course:
            course_id = self._extract_subscription_course_info(url)
            course = self._extract_course_info_json(portal_name, course_id, url)

        if course:
            return course.get("id"), portal_name, course
        if not course:
            self.logger.fatal("Downloading course information, course id not found .. ")
            self.logger.fatal(
                "It seems either you are not enrolled or you have to visit the course atleast once while you are logged in.",
            )
            sys.exit(1)

    def print_course_info(self):
        course_title = self.parsed_data.get("title")
        chapter_count = self.parsed_data.get("total_chapters")
        lecture_count = self.parsed_data.get("total_lectures")

        if lecture_count > 100:
            self.logger.warning(
                "This course has a lot of lectures! Fetching all the information can take a long time as well as spams Udemy's servers. It is NOT recommended to continue! Are you sure you want to do this?"
            )
            yn = input("(y/n): ")
            if yn.lower() != "y":
                self.logger.info("Probably wise. Please remove the --info argument and try again.")
                sys.exit(0)

        self.logger.info("> Course: {}".format(course_title))
        self.logger.info("> Total Chapters: {}".format(chapter_count))
        self.logger.info("> Total Lectures: {}".format(lecture_count))
        self.logger.info("\n")

        chapters = self.parsed_data.get("chapters")
        for chapter in chapters:
            chapter_title = chapter.get("chapter_title")
            chapter_index = chapter.get("chapter_index")
            chapter_lecture_count = chapter.get("lecture_count")
            chapter_lectures = chapter.get("lectures")

            # Skip chapters not in the filter if a filter is provided
            if self.chapter_filter is not None and int(chapter_index) not in self.chapter_filter:
                continue

            self.logger.info("> Chapter: {} ({} of {})".format(chapter_title, chapter_index, chapter_count))

            for lecture in chapter_lectures:
                lecture_index = lecture.get("lecture_index")  # this is the raw object index from udemy
                lecture_title = lecture.get("lecture_title")
                parsed_lecture = self._parse_lecture(lecture)

                lecture_sources = parsed_lecture.get("sources")
                lecture_is_encrypted = parsed_lecture.get("is_encrypted", None)
                lecture_extension = parsed_lecture.get("extension")
                lecture_asset_count = parsed_lecture.get("assets_count")
                lecture_subtitles = parsed_lecture.get("subtitles")
                lecture_video_sources = parsed_lecture.get("video_sources")
                lecture_type = parsed_lecture.get("type")

                lecture_qualities = []

                if lecture_sources:
                    lecture_sources = sorted(lecture_sources, key=lambda x: int(x.get("height")), reverse=True)
                if lecture_video_sources:
                    lecture_video_sources = sorted(
                        lecture_video_sources, key=lambda x: int(x.get("height")), reverse=True
                    )

                if lecture_is_encrypted and lecture_video_sources != None:
                    lecture_qualities = [
                        "{}@{}x{}".format(x.get("type"), x.get("width"), x.get("height")) for x in lecture_video_sources
                    ]
                elif lecture_is_encrypted == False and lecture_sources != None:
                    lecture_qualities = [
                        "{}@{}x{}".format(x.get("type"), x.get("height"), x.get("width")) for x in lecture_sources
                    ]

                if lecture_extension:
                    continue

                self.logger.info(
                    "  > Lecture: {} ({} of {})".format(lecture_title, lecture_index, chapter_lecture_count)
                )
                self.logger.info("    > Type: {}".format(lecture_type))
                if lecture_is_encrypted != None:
                    self.logger.info("    > DRM: {}".format(lecture_is_encrypted))
                if lecture_asset_count:
                    self.logger.info("    > Asset Count: {}".format(lecture_asset_count))
                if lecture_subtitles:
                    self.logger.info(
                        "    > Captions: {}".format(", ".join([x.get("language") for x in lecture_subtitles]))
                    )
                if lecture_qualities:
                    self.logger.info("    > Qualities: {}".format(lecture_qualities))

            if chapter_index != chapter_count:
                self.logger.info("==========================================")

    def _parse_lecture(self, lecture: dict):
        retVal = []

        index = lecture.get("index")  # this is lecture_counter
        lecture_data = lecture.get("data")
        asset = lecture_data.get("asset")
        supp_assets = lecture_data.get("supplementary_assets")

        if isinstance(asset, dict):
            asset_type = asset.get("asset_type").lower() or asset.get("assetType").lower()
            if asset_type == "article":
                retVal.extend(self._extract_article(asset, index))
            elif asset_type == "video":
                pass
            elif asset_type == "e-book":
                retVal.extend(self._extract_ebook(asset, index))
            elif asset_type == "file":
                retVal.extend(self._extract_file(asset, index))
            elif asset_type == "presentation":
                retVal.extend(self._extract_ppt(asset, index))
            elif asset_type == "audio":
                retVal.extend(self._extract_audio(asset, index))
            else:
                self.logger.warning(f"Unknown asset type: {asset_type}")

            if isinstance(supp_assets, list) and len(supp_assets) > 0:
                retVal.extend(self._extract_supplementary_assets(supp_assets, index))

        if asset != None:
            stream_urls = asset.get("stream_urls")
            if stream_urls != None:
                # not encrypted
                if stream_urls and isinstance(stream_urls, dict):
                    sources = stream_urls.get("Video")
                    tracks = asset.get("captions")
                    # duration = asset.get("time_estimation")
                    sources = self._extract_sources(sources, self.skip_hls)
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
                        "type": asset.get("asset_type"),
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
                        "type": asset.get("asset_type"),
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
                        "type": asset.get("asset_type"),
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
                        "type": asset.get("asset_type"),
                    }
        else:
            lecture = {
                **lecture,
                "assets": retVal,
                "assets_count": len(retVal),
                "asset_id": lecture_data.get("id"),
                "type": lecture_data.get("type"),
            }

        return lecture

    def process_parsed_content(self):
        total_chapters = self.parsed_data.get("total_chapters")
        total_lectures = self.parsed_data.get("total_lectures")
        self.logger.info(f"Chapter(s) ({total_chapters})")
        self.logger.info(f"Lecture(s) ({total_lectures})")

        course_name = (
            str(self.parsed_data.get("course_id")) if self.id_as_course_name else self.parsed_data.get("course_title")
        )
        course_dir = self.download_dir / sanitize_filename(course_name)
        course_dir.mkdir(parents=True, exist_ok=True)

        for chapter in self.parsed_data.get("chapters"):
            chapter_title: str = chapter.get("chapter_title")
            chapter_index = chapter.get("chapter_index")

            # Skip chapters not in the filter if a filter is provided
            if self.chapter_filter is not None and int(chapter_index) not in self.chapter_filter:
                self.logger.info("Skipping chapter %s as it is not in the specified filter", chapter_index)
                continue

            chapter_dir = course_dir / chapter_title
            chapter_dir.mkdir(parents=True, exist_ok=True)

            self.logger.info(f"======= Processing chapter {chapter_index} of {total_chapters} =======")

            for lecture in chapter.get("lectures"):
                clazz = lecture.get("_class")

                if clazz == "quiz":
                    # skip the quiz if we dont want to download it
                    if not self.dl_quizzes:
                        continue
                    self.process_quiz(lecture, chapter_dir)
                    continue

                index = lecture.get("index")  # this is lecture_counter
                # lecture_index = lecture.get("lecture_index")  # this is the raw object index from udemy

                lecture_title = lecture.get("lecture_title")
                parsed_lecture = self._parse_lecture(lecture)

                lecture_extension = parsed_lecture.get("extension")
                extension = "mp4"  # video lectures dont have an extension property, so we assume its mp4
                if lecture_extension != None:
                    # if the lecture extension property isnt none, set the extension to the lecture extension
                    extension = lecture_extension
                lecture_file_name = sanitize_filename(lecture_title + "." + extension)
                lecture_file_name = deEmojify(lecture_file_name)
                lecture_path = chapter_dir / lecture_file_name

                if not self.skip_lectures:
                    self.logger.info(f"  > Processing lecture {index} of {total_lectures}")

                    # Check if the lecture is already downloaded
                    if lecture_path.is_file():
                        self.logger.info("      > Lecture '%s' is already downloaded, skipping..." % lecture_title)
                    else:
                        # Check if the file is an html file
                        if extension == "html":
                            # if the html content is None or an empty string, skip it so we dont save empty html files
                            if parsed_lecture.get("html_content") != None and parsed_lecture.get("html_content") != "":
                                html_content = (
                                    parsed_lecture.get("html_content").encode("utf8", "ignore").decode("utf8")
                                )
                                lecture_path = chapter_dir / "{}.html".format(sanitize_filename(lecture_title))
                                try:
                                    with lecture_path.open(mode="w", encoding="utf8") as f:
                                        f.write(html_content)
                                except Exception:
                                    self.logger.exception("    > Failed to write html file")
                        else:
                            self.process_lecture(parsed_lecture, lecture_path, chapter_dir)

                # download subtitles for this lecture
                subtitles = parsed_lecture.get("subtitles")
                if self.download_captions and subtitles != None and lecture_extension == None:
                    self.logger.info("Processing {} caption(s)...".format(len(subtitles)))
                    for subtitle in subtitles:
                        lang = subtitle.get("language")
                        if lang == self.lang or self.lang == "all":
                            self.process_caption(subtitle, lecture_title, chapter_dir)

                if self.download_assets:
                    assets = parsed_lecture.get("assets")
                    self.logger.info("    > Processing {} asset(s) for lecture...".format(len(assets)))

                    for asset in assets:
                        asset_type = asset.get("type")
                        file_path = asset.get("filename")
                        download_url = asset.get("download_url")

                        if asset_type == "article":
                            body = asset.get("body")
                            # stip the 03d prefix
                            lecture_path = os.path.join(chapter_dir, "{}.html".format(sanitize_filename(lecture_title)))
                            try:
                                with open("./templates/article_template.html", "r") as f:
                                    content = f.read()
                                    content = content.replace("__title_placeholder__", lecture_title[4:])
                                    content = content.replace("__data_placeholder__", body)
                                    with open(lecture_path, encoding="utf8", mode="w") as f:
                                        f.write(content)
                            except Exception as e:
                                print("Failed to write html file: ", e)
                                continue
                        elif asset_type == "video":
                            self.logger.warning(
                                "If you're seeing this message, that means that you reached a secret area that I haven't finished! jk I haven't implemented handling for this asset type, please report this at https://github.com/Puyodead1/udemy-downloader/issues so I can add it. When reporting, please provide the following information: "
                            )
                            self.logger.warning("AssetType: Video; AssetData: ", asset)
                        elif (
                            asset_type == "audio"
                            or asset_type == "e-book"
                            or asset_type == "file"
                            or asset_type == "presentation"
                            or asset_type == "ebook"
                            or asset_type == "source_code"
                        ):
                            try:
                                ret_code = download_aria(download_url, chapter_dir, file_path)
                                self.logger.debug(f"      > Download return code: {ret_code}")
                            except Exception:
                                self.logger.exception("> Error downloading asset")
                        elif asset_type == "external_link":
                            # write the external link to a shortcut file
                            file_path = chapter_dir / f"{file_path}.url"

                            with file_path.open(mode="w") as f:
                                f.write("[InternetShortcut]\n")
                                f.write(f"URL={download_url}")

                            # save all the external links to a single file
                            savedirs, name = os.path.split(os.path.join(chapter_dir, file_path))
                            file_path = "external-links.txt"
                            file_path = Path(savedirs, file_path)
                            file_data = []
                            if file_path.is_file():
                                file_data = [
                                    i.strip().lower() for i in open(file_path, encoding="utf-8", errors="ignore") if i
                                ]

                            content = "\n{}\n{}\n".format(name, download_url)
                            if name.lower() not in file_data:
                                with file_path.open(mode="a", encoding="utf-8", errors="ignore") as f:
                                    f.write(content)

    def parse_course_data(self):
        self.parsed_data["bearer_token"] = self.bearer_token
        self.parsed_data["course_id"] = self.course_id
        self.parsed_data["title"] = self.course_title
        self.parsed_data["course_title"] = self.course_slug
        self.parsed_data["chapters"] = []
        self.parsed_data["portal_name"] = self.portal_name
        chapter_index_counter = -1

        course = self.course_data.get("results")
        resource = self.course_data.get("detail")

        if resource:
            self.logger.info("> Terminating Session...")
            self.session.terminate()
            self.logger.info("> Session Terminated.")

        if course:
            self.logger.info("> Processing course data, this may take a minute. ")
            lecture_counter = 0
            lectures = []

            for entry in course:
                clazz = entry.get("_class")

                if clazz == "chapter":
                    # reset lecture tracking
                    if not self.use_continuous_lecture_numbers:
                        lecture_counter = 0
                    lectures = []

                    chapter_index = entry.get("object_index")
                    chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))

                    if chapter_title not in self.parsed_data["chapters"]:
                        self.parsed_data["chapters"].append(
                            {
                                "chapter_title": chapter_title,
                                "chapter_id": entry.get("id"),
                                "chapter_index": chapter_index,
                                "lectures": [],
                            }
                        )
                        chapter_index_counter += 1
                elif clazz == "lecture":
                    lecture_counter += 1
                    lecture_id = entry.get("id")
                    if len(self.parsed_data["chapters"]) == 0:
                        # dummy chapters to handle lectures without chapters
                        chapter_index = entry.get("object_index")
                        chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))
                        if chapter_title not in self.parsed_data["chapters"]:
                            self.parsed_data["chapters"].append(
                                {
                                    "chapter_title": chapter_title,
                                    "chapter_id": lecture_id,
                                    "chapter_index": chapter_index,
                                    "lectures": [],
                                }
                            )
                            chapter_index_counter += 1
                    if lecture_id:
                        self.logger.info(f"Processing {course.index(entry) + 1} of {len(course)}")

                        lecture_index = entry.get("object_index")
                        lecture_title = "{0:03d} ".format(lecture_counter) + sanitize_filename(entry.get("title"))

                        lectures.append(
                            {
                                "index": lecture_counter,
                                "lecture_index": lecture_index,
                                "lecture_title": lecture_title,
                                "_class": entry.get("_class"),
                                "id": lecture_id,
                                "data": entry,
                            }
                        )
                    else:
                        self.logger.debug("Lecture: ID is None, skipping")
                elif clazz == "quiz":
                    lecture_counter += 1
                    lecture_id = entry.get("id")
                    if len(self.parsed_data["chapters"]) == 0:
                        # dummy chapters to handle lectures without chapters
                        chapter_index = entry.get("object_index")
                        chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))
                        if chapter_title not in self.parsed_data["chapters"]:
                            self.parsed_data["chapters"].append(
                                {
                                    "chapter_title": chapter_title,
                                    "chapter_id": lecture_id,
                                    "chapter_index": chapter_index,
                                    "lectures": [],
                                }
                            )
                            chapter_index_counter += 1

                    if lecture_id:
                        self.logger.info(f"Processing {course.index(entry) + 1} of {len(course)}")

                        lecture_index = entry.get("object_index")
                        lecture_title = "{0:03d} ".format(lecture_counter) + sanitize_filename(entry.get("title"))

                        lectures.append(
                            {
                                "index": lecture_counter,
                                "lecture_index": lecture_index,
                                "lecture_title": lecture_title,
                                "_class": entry.get("_class"),
                                "id": lecture_id,
                                "data": entry,
                            }
                        )
                    else:
                        self.logger.debug("Quiz: ID is None, skipping")

                self.parsed_data["chapters"][chapter_index_counter]["lectures"] = lectures
                self.parsed_data["chapters"][chapter_index_counter]["lecture_count"] = len(lectures)

            self.parsed_data["total_chapters"] = len(self.parsed_data["chapters"])
            self.parsed_data["total_lectures"] = sum(
                [entry.get("lecture_count", 0) for entry in self.parsed_data["chapters"] if entry]
            )

        if self.save_to_file:
            self.save_parsed_file()
            self.logger.info("> Saved parsed data to json")

        if self.info:
            self.print_course_info()
        else:
            self.process_parsed_content()

    def process_lecture(self, lecture: dict, lecture_path: Path, chapter_dir: Path):
        lecture_id = lecture.get("id")
        lecture_title = lecture.get("lecture_title")
        is_encrypted = lecture.get("is_encrypted")
        lecture_sources = lecture.get("video_sources")

        if is_encrypted:
            if len(lecture_sources) > 0:
                source = lecture_sources[-1]  # last index is the best quality
                if isinstance(self.quality, int):
                    source = min(lecture_sources, key=lambda x: abs(int(x.get("height")) - self.quality))
                self.logger.info(f"      > Lecture '{lecture_title}' has DRM, attempting to download. Selected quality: {source.get('height')}")
                self.handle_segments(
                    source.get("download_url"),
                    source.get("format_id"),
                    str(lecture_id),
                    lecture_title,
                    lecture_path,
                    chapter_dir,
                )
            else:
                self.logger.info(f"      > Lecture '{lecture_title}' is missing media links")
                self.logger.debug(f"Lecture source count: {len(lecture_sources)}")
        else:
            sources = lecture.get("sources")
            sources = sorted(sources, key=lambda x: int(x.get("height")), reverse=True)
            if sources:
                if not os.path.isfile(lecture_path):
                    self.logger.info("      > Lecture doesn't have DRM, attempting to download...")
                    source = sources[0]  # first index is the best quality
                    if isinstance(self.quality, int):
                        source = min(sources, key=lambda x: abs(int(x.get("height")) - self.quality))
                    try:
                        self.logger.info(
                            "      ====== Selected quality: %s %s", source.get("type"), source.get("height")
                        )
                        url = source.get("download_url")
                        source_type = source.get("type")
                        if source_type == "hls":
                            temp_filepath = str(lecture_path).replace(".mp4", ".%(ext)s")
                            cmd = [
                                "yt-dlp",
                                "--enable-file-urls",
                                "--force-generic-extractor",
                                "--concurrent-fragments",
                                f"{self.concurrent_downloads}",
                                "--downloader",
                                "aria2c",
                                "--downloader-args",
                                'aria2c:"--disable-ipv6"',
                                "-o",
                                f"{temp_filepath}",
                                f"{url}",
                            ]
                            process = subprocess.Popen(cmd)
                            log_subprocess_output("YTDLP-STDOUT", process.stdout)
                            log_subprocess_output("YTDLP-STDERR", process.stderr)
                            ret_code = process.wait()
                            if ret_code == 0:
                                tmp_file_path = str(lecture_path) + ".tmp"
                                self.logger.info("      > HLS Download success")
                                if self.use_h265:
                                    codec = "hevc_nvenc" if self.use_nvenc else "libx265"
                                    transcode = (
                                        "-hwaccel cuda -hwaccel_output_format cuda".split(" ") if self.use_nvenc else []
                                    )
                                    cmd = [
                                        "ffmpeg",
                                        *transcode,
                                        "-y",
                                        "-i",
                                        lecture_path,
                                        "-c:v",
                                        codec,
                                        "-c:a",
                                        "copy",
                                        "-f",
                                        "mp4",
                                        tmp_file_path,
                                    ]
                                    process = subprocess.Popen(cmd)
                                    log_subprocess_output("FFMPEG-STDOUT", process.stdout)
                                    log_subprocess_output("FFMPEG-STDERR", process.stderr)
                                    ret_code = process.wait()
                                    if ret_code == 0:
                                        os.unlink(lecture_path)
                                        os.rename(tmp_file_path, lecture_path)
                                        self.logger.info("      > Encoding complete")
                                    else:
                                        self.logger.error("      > Encoding returned non-zero return code")
                        else:
                            ret_code = download_aria(url, chapter_dir, lecture_title + ".mp4")
                            self.logger.debug(f"      > Download return code: {ret_code}")
                    except Exception:
                        self.logger.exception(f">        Error downloading lecture")
                else:
                    self.logger.info(f"      > Lecture '{lecture_title}' is already downloaded, skipping...")
            else:
                self.logger.error("      > Missing sources for lecture", lecture)

    def handle_segments(
        self, url: str, format_id, lecture_id: str, video_title: str, output_path: Path, chapter_dir: Path
    ):
        os.chdir(chapter_dir)

        video_filepath_enc = lecture_id + ".encrypted.mp4"
        audio_filepath_enc = lecture_id + ".encrypted.m4a"
        temp_output_path = chapter_dir / (lecture_id + ".mp4")

        self.logger.info("> Downloading Lecture Tracks...")
        args = [
            "yt-dlp",
            "--enable-file-urls",
            "--force-generic-extractor",
            "--allow-unplayable-formats",
            "--concurrent-fragments",
            f"{self.concurrent_downloads}",
            "--downloader",
            "aria2c",
            "--downloader-args",
            'aria2c:"--disable-ipv6"',
            "--fixup",
            "never",
            "-k",
            "-o",
            f"{lecture_id}.encrypted.%(ext)s",
            "-f",
            format_id,
            f"{url}",
        ]
        process = subprocess.Popen(args)
        log_subprocess_output("YTDLP-STDOUT", process.stdout)
        log_subprocess_output("YTDLP-STDERR", process.stderr)
        ret_code = process.wait()
        self.logger.info("> Lecture Tracks Downloaded")

        if ret_code != 0:
            self.logger.warning("Return code from the downloader was non-0 (error), skipping!")
            return

        audio_kid = None
        video_kid = None

        try:
            video_kid = extract_kid(video_filepath_enc)
            self.logger.info("KID for video file is: " + video_kid)
        except Exception:
            self.logger.exception(f"Error extracting video kid")
            return

        try:
            audio_kid = extract_kid(audio_filepath_enc)
            self.logger.info("KID for audio file is: " + audio_kid)
        except Exception:
            self.logger.exception(f"Error extracting audio kid")
            return

        audio_key = None
        video_key = None

        if audio_kid is not None:
            try:
                audio_key = self.keys[audio_kid]
            except KeyError:
                self.logger.error(
                    f"Audio key not found for {audio_kid}, if you have the key then you probably didn't add them to the key file correctly."
                )
                return

        if video_kid is not None:
            try:
                video_key = self.keys[video_kid]
            except KeyError:
                self.logger.error(
                    f"Video key not found for {audio_kid}, if you have the key then you probably didn't add them to the key file correctly."
                )
                return

        try:
            # logger.info("> Decrypting video, this might take a minute...")
            # ret_code = decrypt(video_kid, video_filepath_enc, video_filepath_dec)
            # if ret_code != 0:
            #     logger.error("> Return code from the decrypter was non-0 (error), skipping!")
            #     return
            # logger.info("> Decryption complete")
            # logger.info("> Decrypting audio, this might take a minute...")
            # decrypt(audio_kid, audio_filepath_enc, audio_filepath_dec)
            # if ret_code != 0:
            #     logger.error("> Return code from the decrypter was non-0 (error), skipping!")
            #     return
            # logger.info("> Decryption complete")
            self.logger.info("> Merging video and audio, this might take a minute...")
            self.mux_process(
                video_filepath_enc, audio_filepath_enc, video_title, temp_output_path, audio_key, video_key
            )
            if ret_code != 0:
                self.logger.error("> Return code from ffmpeg was non-0 (error), skipping!")
                return
            self.logger.info("> Merging complete, renaming final file...")
            temp_output_path.rename(output_path)
            self.logger.info("> Cleaning up temporary files...")
            os.remove(video_filepath_enc)
            os.remove(audio_filepath_enc)
        except Exception as e:
            self.logger.exception(f"Muxing error: {e}")
        finally:
            os.chdir(self.home)
            # if the url is a file url, we need to remove the file after we're done with it
            if url.startswith("file://"):
                try:
                    os.unlink(url[7:])
                except:
                    pass

    def mux_process(
        self,
        video_filepath: str,
        audio_filepath: str,
        video_title: str,
        output_path: str,
        audio_key: Union[str | None] = None,
        video_key: Union[str | None] = None,
    ):
        codec = "hevc_nvenc" if self.use_nvenc else "libx265"
        transcode = "-hwaccel cuda -hwaccel_output_format cuda" if self.use_nvenc else ""
        audio_decryption_arg = f"-decryption_key {audio_key}" if audio_key is not None else ""
        video_decryption_arg = f"-decryption_key {video_key}" if video_key is not None else ""

        if os.name == "nt":
            if self.use_h265:
                command = f'ffmpeg {transcode} -y {video_decryption_arg} -i "{video_filepath}" {audio_decryption_arg} -i "{audio_filepath}" -c:v {codec} -vtag hvc1 -crf {self.h265_crf} -preset {self.h265_preset} -c:a copy -fflags +bitexact -shortest -map_metadata -1 -metadata title="{video_title}" "{output_path}"'
            else:
                command = f'ffmpeg -y {video_decryption_arg} -i "{video_filepath}" {audio_decryption_arg} -i "{audio_filepath}" -c copy -fflags +bitexact -shortest -map_metadata -1 -metadata title="{video_title}" "{output_path}"'
        else:
            if use_h265:
                command = f'nice -n 7 ffmpeg {transcode} -y {video_decryption_arg} -i "{video_filepath}" {audio_decryption_arg} -i "{audio_filepath}" -c:v {codec} -vtag hvc1 -crf {h265_crf} -preset {h265_preset} -c:a copy -fflags +bitexact -shortest -map_metadata -1 -metadata title="{video_title}" "{output_path}"'
            else:
                command = f'nice -n 7 ffmpeg -y {video_decryption_arg} -i "{video_filepath}" {audio_decryption_arg} -i "{audio_filepath}" -c copy -fflags +bitexact -shortest -map_metadata -1 -metadata title="{video_title}" "{output_path}"'

        process = subprocess.Popen(command, shell=True)
        log_subprocess_output("FFMPEG-STDOUT", process.stdout)
        log_subprocess_output("FFMPEG-STDERR", process.stderr)
        ret_code = process.wait()
        if ret_code != 0:
            raise Exception("Muxing returned a non-zero exit code")

        return ret_code

    def process_caption(self, caption, lecture_title: str, lecture_dir: Path, tries=0):
        filename = f"%s_%s.%s" % (sanitize_filename(lecture_title), caption.get("language"), caption.get("extension"))
        filename_no_ext = f"%s_%s" % (sanitize_filename(lecture_title), caption.get("language"))
        filepath = lecture_dir / filename

        if filepath.is_file():
            self.logger.info("    > Caption '%s' already downloaded." % filename)
        else:
            self.logger.info(f"    >  Downloading caption: '%s'" % filename)
            try:
                ret_code = download_aria(caption.get("download_url"), lecture_dir, filename)
                self.logger.debug(f"      > Download return code: {ret_code}")
            except Exception as e:
                if tries >= 3:
                    self.logger.error(f"    > Error downloading caption: {e}. Exceeded retries, skipping.")
                    return
                else:
                    self.logger.error(f"    > Error downloading caption: {e}. Will retry {3-tries} more times.")
                    self.process_caption(caption, lecture_title, lecture_dir, tries + 1)
            if caption.get("extension") == "vtt":
                try:
                    self.logger.info("    > Converting caption to SRT format...")
                    convert(lecture_dir, filename_no_ext)
                    self.logger.info("    > Caption conversion complete.")
                    if not self.keep_vtt:
                        filepath.unlink()
                except Exception:
                    self.logger.exception(f"    > Error converting caption")

    def process_quiz(self, lecture, chapter_dir: Path):
        quiz = self._get_quiz_with_info(lecture.get("id"))
        if quiz["_type"] == "coding-problem":
            self.process_coding_assignment(quiz, lecture, chapter_dir)
        else:  # Normal quiz
            self.process_normal_quiz(quiz, lecture, chapter_dir)

    def process_normal_quiz(self, quiz, lecture, chapter_dir: Path):
        lecture_title = lecture.get("lecture_title")
        lecture_index = lecture.get("lecture_index")
        lecture_file_name = sanitize_filename(lecture_title + ".html")
        lecture_path = chapter_dir / lecture_file_name

        self.logger.info(f"  > Processing quiz {lecture_index}")
        with open("./templates/quiz_template.html", "r") as f:
            html = f.read()
            quiz_data = {
                "quiz_id": lecture["data"].get("id"),
                "quiz_description": lecture["data"].get("description"),
                "quiz_title": lecture["data"].get("title"),
                "pass_percent": lecture.get("data").get("pass_percent"),
                "questions": quiz["contents"],
            }
            html = html.replace("__data_placeholder__", json.dumps(quiz_data))
            with lecture_path.open(mode="w") as f:
                f.write(html)

    def process_coding_assignment(self, quiz, lecture, chapter_dir: Path):
        lecture_title = lecture.get("lecture_title")
        lecture_index = lecture.get("lecture_index")
        lecture_file_name = sanitize_filename(lecture_title + ".html")
        lecture_path = chapter_dir / lecture_file_name

        self.logger.info(f"  > Processing quiz {lecture_index} (coding assignment)")

        with open("./templates/coding_assignment_template.html", "r") as f:
            html = f.read()
            quiz_data = {
                "title": lecture_title,
                "hasInstructions": quiz["hasInstructions"],
                "hasTests": quiz["hasTests"],
                "hasSolutions": quiz["hasSolutions"],
                "instructions": quiz["contents"]["instructions"],
                "tests": quiz["contents"]["tests"],
                "solutions": quiz["contents"]["solutions"],
            }
            html = html.replace("__data_placeholder__", json.dumps(quiz_data))
            with lecture_path.open(mode="w") as f:
                f.write(html)
