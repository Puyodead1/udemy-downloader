import html
import json
import logging
import math
import os
import random
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
from curl_cffi import requests
from pathvalidate import sanitize_filename
from pywidevine.cdm import Cdm
from pywidevine.device import Device

from udemy_downloader.constants import (
    COLLECTION_URL,
    COURSE_SEARCH,
    COURSE_URL,
    CURRICULUM_ITEMS_PARAMS,
    CURRICULUM_ITEMS_URL,
    LECTURE_URL,
    LICENSE_URL,
    LOGGER_NAME,
    MY_COURSES_URL,
    PRACTICE_COMPONENTS_URL,
    PRACTICE_QUESTIONS_URL,
    PRACTICE_SUPPLEMENTARY_ASSET_URL,
    PRACTICE_URL,
    PRACTICE_VIDEO_ASSET_URL,
    QUIZ_URL,
    ROLE_PLAY_URL,
    SUBSCRIPTION_COURSES_URL,
)
from udemy_downloader.Session import Session
from udemy_downloader.UdemyAuth import UdemyAuth
from udemy_downloader.utils import (
    check_for_aria,
    check_for_ffmpeg,
    deEmojify,
    download_aria,
    log_subprocess_output,
    extract_role_play,
    parse_chapter_filter,
    extract_pssh,
    fix_empty_saiz,
)
from udemy_downloader.vtt_to_srt import convert

# asset_type -> (key in download_urls, parsed asset type)
DOWNLOADABLE_ASSETS = {
    "e-book": ("E-Book", "ebook"),
    "file": ("File", "file"),
    "presentation": ("Presentation", "presentation"),
    "audio": ("Audio", "audio"),
}

HEIGHT_TO_WIDTH = {
    "2160": "3840",
    "1440": "2560",
    "1080": "1920",
    "720": "1280",
    "480": "854",
    "360": "640",
    "240": "426",
}


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
        out: Union[str, None],
        use_continuous_lecture_numbers: bool,
        chapter_filter_raw: Union[str, None] = None,
        device: Union[str, None] = None,
        assume_yes: bool = False,
    ):
        self.chapter_filter = None
        self.keys: dict[str, str] = {}
        self.session: Union[Session, None] = None
        self.cj: CookieJar = None
        self.logger: logging.Logger
        self.auth = UdemyAuth()
        self.parsed_data = {}

        self.home_dir = Path(os.getcwd())
        self.devices_dir = self.home_dir / "devices"
        self.download_dir = self.home_dir / "downloads"
        self.saved_dir = self.home_dir / "saved"
        self.key_file_path = self.home_dir / "keyfile.json"
        self.cookies_path = self.home_dir / "cookies.txt"
        self.log_dir = self.home_dir / "logs"
        self.log_file_path = self.log_dir / f"{time.strftime('%Y-%m-%d-%I-%M-%S')}.log"
        self.log_format = "[%(asctime)s] [%(name)s] [%(funcName)s:%(lineno)d] %(levelname)s: %(message)s"
        self.log_date_format = "%I:%M:%S"
        self.log_level_str = log_level_str

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.saved_dir.mkdir(parents=True, exist_ok=True)
        self.devices_dir.mkdir(parents=True, exist_ok=True)

        self.init_logger()

        self.bearer_token = bearer_token
        self.browser = browser
        self.is_subscription_course = is_subscription_course
        self.skip_hls = skip_hls
        self.download_assets = download_assets
        self.lang = lang
        if not lang and download_captions:
            self.logger.warning(
                "You have requested captions be downloaded but have not specified a language, defaulting to English (en)."
            )
            self.lang = "en"
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
        self.id_as_course_name = id_as_course_name
        self.assume_yes = assume_yes
        self.out = out
        self.use_continuous_lecture_numbers = use_continuous_lecture_numbers
        self.device = None

        # Process the chapter filter
        if chapter_filter_raw:
            self.chapter_filter = parse_chapter_filter(chapter_filter_raw)
            self.logger.info("Chapter filter applied: %s", sorted(self.chapter_filter))

        if device:
            self.device_path = self.devices_dir / f"{device}.wvd"
            if not self.device_path.exists():
                self.logger.error(
                    f"Device file {self.device_path.relative_to(self.home_dir)} not found!"
                )
                sys.exit(1)
            self.device = Device.load(self.device_path)
            self.cdm = Cdm.from_device(self.device)

    def init_logger(self):
        # parse the log level string to a log level
        self.log_level = getattr(logging, self.log_level_str.upper(), logging.INFO)

        # create a colored formatter for the console
        console_formatter = ColoredFormatter(
            self.log_format, datefmt=self.log_date_format
        )
        # create a regular non-colored formatter for the log file
        file_formatter = logging.Formatter(
            self.log_format, datefmt=self.log_date_format
        )

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
        match = re.search(r"ffmpeg version (\d+)\.(\d+)", ffmpeg_version or "")
        if match:
            major_version = int(match.group(1))  # major version
            minor_version = int(match.group(2))  # minor version
            if major_version >= 5:
                self.logger.info(
                    f"Found FFmpeg version {major_version}.{minor_version}"
                )
            else:
                self.logger.fatal(
                    f"FFmpeg version {major_version}.{minor_version} is too old! Please update to version 5 or higher."
                )
                sys.exit(1)
        else:
            self.logger.warning("Failed to extract FFmpeg version.")

    def visit(self):
        portal_name, _ = self.extract_course_name(self.course_url)
        if not self.auth._session.visit(portal_name):
            self.logger.fatal(
                "> Visit request failed, Udemy's Cloudflare protection may be blocking requests. Try again later."
            )
            sys.exit(1)

    def update_auth(self):
        if not self.session:
            self.session = self.auth.update_token(self.bearer_token)

        # if the session is still None, use cookie auth
        if not self.session:
            if self.browser == None:
                self.logger.error(
                    "No bearer token was provided, and no browser for cookie extraction was specified."
                )
                sys.exit(1)

            # --browser was given, so using cookies is expected rather than worth a warning
            self.logger.debug(
                "No bearer token was provided, attempting to use browser cookies."
            )

            self.session = self.auth._session

            if self.browser == "file":
                # load netscape cookies from file
                self.cj = MozillaCookieJar(self.cookies_path)
                # exported cookie files mark session cookies with expiry 0, which python treats as expired,
                # so load everything and only drop cookies that really have expired
                self.cj.load(ignore_discard=True, ignore_expires=True)
                now = time.time()
                for cookie in list(self.cj):
                    if cookie.expires and cookie.expires < now:
                        self.cj.clear(cookie.domain, cookie.path, cookie.name)
            else:
                # argparse limits browser to names browser_cookie3 provides a loader for
                self.cj = getattr(browser_cookie3, self.browser)(domain_name="udemy.com")

            self.session.set_cookiejar(self.cj)

        # the app's basic auth header is replaced by the bearer token (X-Udemy-Authorization) or cookies
        self.session._headers.pop("authorization", None)

    def get_course_info(self):
        self.logger.info("> Fetching course information, this may take a minute...")
        if not self.load_from_file:
            course_id, portal_name, course_info = self.extract_course_info(
                self.course_url
            )
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
            self.course_data = self.extract_course_content(
                self.portal_name, self.course_id, self.course_url
            )
            self.course_data["portal_name"] = self.portal_name

        chapter_count = len(
            [x for x in self.course_data["results"] if x["_class"] == "chapter"]
        )
        lecture_count = len(
            [x for x in self.course_data["results"] if x["_class"] == "lecture"]
        )

        self.logger.info(
            f"> Successfully fetched {chapter_count} chapters and {lecture_count} lectures for '{self.course_title}'"
        )

    def save_content_file(self):
        course_data = self.course_data.copy()
        course_data["course_id"] = self.course_id
        course_data["course_title"] = self.course_title
        course_data["course_slug"] = self.course_slug
        course_data["portal_name"] = self.portal_name

        with (self.saved_dir / "course_content.json").open(
            mode="w", encoding="utf8"
        ) as f:
            f.write(json.dumps(course_data))

    def load_content_file(self):
        self.course_data = json.loads(
            (self.saved_dir / "course_content.json")
            .open(mode="r", encoding="utf8")
            .read()
        )

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
        self.parsed_data = json.loads(
            (self.saved_dir / "_udemy.json").open(mode="r", encoding="utf8").read()
        )
        self.course_id = self.parsed_data.get("course_id")
        self.portal_name = self.parsed_data.get("portal_name")
        self.course_title = self.parsed_data.get("course_title")

    def _get_quiz(self, quiz_id: str):
        url = QUIZ_URL.format(portal_name=self.portal_name, quiz_id=quiz_id)
        return self._get_all_pages(url).get("results", [])

    def _get_practice_with_info(self, practice_id: str):
        def url_for(template, **kwargs):
            return template.format(
                portal_name=self.portal_name,
                practice_id=practice_id,
                course_id=self.course_id,
                **kwargs,
            )

        practice = self._get_json(url_for(PRACTICE_URL))
        return {
            "_class": practice.get("_class"),
            "description": practice.get("description"),
            "estimated_duration": practice.get("estimated_duration"),
            "instructions": self._get_all_pages(
                url_for(PRACTICE_COMPONENTS_URL, component_type="instruction")
            ).get("results", []),
            "solutions": self._get_all_pages(
                url_for(PRACTICE_COMPONENTS_URL, component_type="solution")
            ).get("results", []),
            "questions": self._get_all_pages(url_for(PRACTICE_QUESTIONS_URL)).get(
                "results", []
            ),
        }

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

            resp["hasInstructions"] = (
                False if resp["contents"]["instructions"] == "(None)" else True
            )
            resp["hasTests"] = (
                False if isinstance(resp["contents"]["tests"], str) else True
            )
            resp["hasSolutions"] = (
                False if isinstance(resp["contents"]["solutions"], str) else True
            )
        else:  # Normal quiz
            resp["_type"] = "normal-quiz"
            resp["contents"] = quiz_json

        return resp

    def _extract_download(
        self,
        asset: dict,
        lecture_counter: int,
        url_key: str,
        asset_type: str,
        title: Union[str, None] = None,
    ):
        """extracts a downloadable asset, url_key is its key in download_urls (e.g. File, E-Book)"""
        download_urls = asset.get("download_urls")
        if not download_urls or not isinstance(download_urls, dict):
            return []
        filename = asset.get("filename")
        entry = {
            "type": asset_type,
            "filename": "{0:03d} ".format(lecture_counter) + filename,
            "extension": filename.rsplit(".", 1)[-1] if "." in filename else "",
            "download_url": download_urls.get(url_key, [])[0].get("file"),
            "id": asset.get("id"),
        }
        if title is not None:
            entry["title"] = title
        return [entry]

    def _extract_supplementary_assets(self, supp_assets: list, lecture_counter: int):
        _temp = []
        for entry in supp_assets:
            title = sanitize_filename(entry.get("title"))
            asset_type = entry.get("asset_type").lower()
            if asset_type == "file":
                _temp.extend(
                    self._extract_download(entry, lecture_counter, "File", "file", title)
                )
            elif asset_type == "sourcecode":
                _temp.extend(
                    self._extract_download(
                        entry, lecture_counter, "SourceCode", "source_code", title
                    )
                )
            elif asset_type == "externallink":
                _temp.append(
                    {
                        "type": "external_link",
                        "title": title,
                        "filename": "{0:03d} ".format(lecture_counter)
                        + entry.get("filename"),
                        "extension": "txt",
                        "download_url": entry.get("external_url"),
                        "id": entry.get("id"),
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
                width = HEIGHT_TO_WIDTH.get(height, "256")
                if (
                    source.get("type") == "application/x-mpegURL"
                    or "m3u8" in download_url
                ):
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
                playlist_path = Path(
                    temp_path, f"index_{asset_id}_{width}x{height}.m3u8"
                )

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
        _temp = []
        try:
            ytdl = yt_dlp.YoutubeDL(
                {
                    "quiet": True,
                    "no_warnings": True,
                    "allow_unplayable_formats": True,
                    "enable_file_urls": True,
                }
            )
            results = ytdl.extract_info(
                url, download=False, force_generic_extractor=True
            )
            formats = results.get("formats", [])
            best_audio = next(
                (
                    f
                    for f in formats
                    if f["acodec"] != "none" and f["vcodec"] == "none"
                ),
                None,
            )
            if not best_audio:
                raise ValueError("No suitable audio format found in MPD")
            audio_format_id = best_audio.get("format_id")

            # for each resolution, use only the highest bitrate video only format
            best_by_height = {}
            for format in formats:
                if format["vcodec"] == "none" or format["acodec"] != "none":
                    continue
                height = format.get("height")
                tbr = round(format.get("tbr") or 0)
                if height in best_by_height and best_by_height[height]["tbr"] >= tbr:
                    continue
                best_by_height[height] = {
                    "type": "dash",
                    "height": str(height),
                    "width": str(format.get("width")),
                    "format_id": f"{format.get('format_id')},{audio_format_id}",
                    "extension": format.get("ext"),
                    "download_url": url,
                    "tbr": tbr,
                }
            _temp = list(best_by_height.values())
        except Exception:
            self.logger.exception("Error fetching MPD streams")

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

    def _get_json(self, url: str, params=None):
        """GET a url and decode the json body, exiting if the request or decoding fails"""
        try:
            r = self.session._get(url, params)
        except requests.exceptions.RequestException as error:
            self.logger.fatal(
                f"Couldn't reach Udemy: {error}. Check your internet connection and try again."
            )
            sys.exit(1)

        auth_hint = "Check that your bearer token or browser cookies are valid and that you're enrolled in this course."
        try:
            data = r.json()
        except ValueError:
            # usually a login, captcha or block page instead of an API response
            hint = (
                auth_hint
                if r.status_code in (401, 403)
                else "Udemy may be blocking the request or having problems, try again later."
            )
            self.logger.fatal(
                f"Udemy returned an unexpected response (HTTP {r.status_code}) for {url}. {hint}"
            )
            self.logger.debug(f"Response body: {r.text[:1000]}")
            sys.exit(1)

        if not r.ok:
            detail = data.get("detail") if isinstance(data, dict) else None
            self.logger.warning(
                f"Udemy returned HTTP {r.status_code} for {url}"
                + (f": {detail.rstrip('.')}" if detail else "")
                + (f". {auth_hint}" if r.status_code in (401, 403) else "")
            )
        return data

    def _get_all_pages(self, url: str, params=None, description: str = "data"):
        """GET a paginated api url and return the first page with every page's results combined"""
        data = self._get_json(url, params)
        if not isinstance(data, dict):
            return {"results": []}
        data.setdefault("results", [])
        _next = data.get("next")
        page_size = len(data["results"]) or 1
        est_page_count = math.ceil((data.get("count") or 0) / page_size)
        page = 1
        while _next:
            page += 1
            self.logger.info(f"> Downloading {description}.. (Page {page}/{est_page_count})")
            resp = self._get_json(_next)
            _next = resp.get("next")
            results = resp.get("results")
            if results and isinstance(results, list):
                data["results"].extend(results)
        return data

    def _subscribed_courses(self, portal_name: str, course_name: str):
        url = COURSE_SEARCH.format(portal_name=portal_name, course_name=course_name)
        return self._get_json(url).get("results", [])

    def _extract_course_info_json(self, portal_name: str, course_id: str, url: str):
        url = COURSE_URL.format(portal_name=portal_name, course_id=course_id)
        return self._get_json(url)

    def extract_course_content(self, portal_name: str, course_id: str, url: str):
        url = CURRICULUM_ITEMS_URL.format(portal_name=portal_name, course_id=course_id)
        return self._get_all_pages(url, CURRICULUM_ITEMS_PARAMS, "course curriculum")

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
        url = MY_COURSES_URL.format(portal_name=portal_name)
        return self._get_all_pages(url, description="your courses").get("results", [])

    def _subscription_course_enrollments(self, portal_name):
        # courses from a subscription plan (e.g. Personal Plan) are listed separately
        url = SUBSCRIPTION_COURSES_URL.format(portal_name=portal_name)
        return self._get_all_pages(url, description="subscription courses").get(
            "results", []
        )

    def _subscribed_collection_courses(self, portal_name: str):
        url = COLLECTION_URL.format(portal_name=portal_name)
        results = self._get_json(url).get("results", [])
        return [
            course
            for collection in results
            for course in collection.get("courses", [])
        ]

    def _archived_courses(self, portal_name):
        url = MY_COURSES_URL.format(portal_name=portal_name)
        return self._get_json(f"{url}&is_archived=true").get("results", [])

    def _extract_subscription_course_info(self, url):
        course_html = self.session._get(url).text
        soup = BeautifulSoup(course_html, "lxml")
        data = soup.find("div", {"class": "ud-component--course-taking--app"})
        if not data:
            self.logger.fatal(
                "Could not find course data. Possible causes are: Missing cookies.txt file, incorrect url (should end with /learn), not logged in to Udemy in specified browser, or not logged into Udemy with the correct account."
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
            results = self._subscribed_courses(
                portal_name=portal_name, course_name=course_name
            )
            course = self._extract_course(response=results, course_name=course_name)
            if not course:
                results = self._my_courses(portal_name=portal_name)
                course = self._extract_course(response=results, course_name=course_name)
            if not course:
                results = self._subscription_course_enrollments(portal_name=portal_name)
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

        if lecture_count > 100 and not self.assume_yes:
            self.logger.warning(
                "This course has a lot of lectures! Fetching all the information can take a long time as well as spams Udemy's servers. It is NOT recommended to continue! Are you sure you want to do this?"
            )
            if not sys.stdin.isatty():
                self.logger.info(
                    "No terminal to confirm in. Re-run with --yes to continue anyway."
                )
                sys.exit(1)
            yn = input("(y/n): ")
            if yn.lower() != "y":
                self.logger.info(
                    "Probably wise. Please remove the --info argument and try again."
                )
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
            if (
                self.chapter_filter is not None
                and int(chapter_index) not in self.chapter_filter
            ):
                continue

            self.logger.info(
                "> Chapter: {} ({} of {})".format(
                    chapter_title, chapter_index, chapter_count
                )
            )

            for lecture in chapter_lectures:
                lecture_index = lecture.get(
                    "lecture_index"
                )  # this is the raw object index from udemy
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
                    lecture_sources = sorted(
                        lecture_sources,
                        key=lambda x: int(x.get("height")),
                        reverse=True,
                    )
                if lecture_video_sources:
                    lecture_video_sources = sorted(
                        lecture_video_sources,
                        key=lambda x: int(x.get("height")),
                        reverse=True,
                    )

                if lecture_is_encrypted and lecture_video_sources != None:
                    lecture_qualities = [
                        "{}@{}x{}".format(
                            x.get("type"), x.get("width"), x.get("height")
                        )
                        for x in lecture_video_sources
                    ]
                elif lecture_is_encrypted == False and lecture_sources != None:
                    lecture_qualities = [
                        "{}@{}x{}".format(
                            x.get("type"), x.get("height"), x.get("width")
                        )
                        for x in lecture_sources
                    ]

                if lecture_extension:
                    continue

                self.logger.info(
                    "  > Lecture: {} ({} of {})".format(
                        lecture_title, lecture_index, chapter_lecture_count
                    )
                )
                self.logger.info("    > Type: {}".format(lecture_type))
                if lecture_is_encrypted != None:
                    self.logger.info("    > DRM: {}".format(lecture_is_encrypted))
                if lecture_asset_count:
                    self.logger.info(
                        "    > Asset Count: {}".format(lecture_asset_count)
                    )
                if lecture_subtitles:
                    self.logger.info(
                        "    > Captions: {}".format(
                            ", ".join([x.get("language") for x in lecture_subtitles])
                        )
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
            asset_type = (
                asset.get("asset_type").lower() or asset.get("assetType").lower()
            )
            if asset_type == "article":
                retVal.extend(self._extract_article(asset, index))
            elif asset_type == "video":
                pass
            elif asset_type in DOWNLOADABLE_ASSETS:
                url_key, download_type = DOWNLOADABLE_ASSETS[asset_type]
                retVal.extend(
                    self._extract_download(asset, index, url_key, download_type)
                )
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
            str(self.parsed_data.get("course_id"))
            if self.id_as_course_name
            else self.parsed_data.get("course_title")
        )
        course_dir = self.download_dir / sanitize_filename(course_name)
        course_dir.mkdir(parents=True, exist_ok=True)

        # lecture counts plus everything that failed, reported once processing finishes
        self.summary = {"downloaded": 0, "already_present": 0, "failed": []}

        for chapter in self.parsed_data.get("chapters"):
            chapter_title: str = chapter.get("chapter_title")
            chapter_index = chapter.get("chapter_index")

            # Skip chapters not in the filter if a filter is provided
            if (
                self.chapter_filter is not None
                and int(chapter_index) not in self.chapter_filter
            ):
                self.logger.info(
                    "Skipping chapter %s as it is not in the specified filter",
                    chapter_index,
                )
                continue

            chapter_dir = course_dir / chapter_title
            chapter_dir.mkdir(parents=True, exist_ok=True)

            self.logger.info(
                f"======= Processing chapter {chapter_index} of {total_chapters} ======="
            )

            for lecture in chapter.get("lectures"):
                clazz = lecture.get("_class")

                if clazz in ("quiz", "practice", "role-play"):
                    # quizzes, practices and role plays are only saved with --download-quizzes
                    if not self.download_quizzes:
                        continue
                    lecture_title = lecture.get("lecture_title")
                    if (chapter_dir / sanitize_filename(lecture_title + ".html")).is_file():
                        self.logger.info(
                            f"      > {clazz.capitalize()} '{lecture_title}' is already downloaded, skipping..."
                        )
                        self.summary["already_present"] += 1
                        continue
                    try:
                        if clazz == "quiz":
                            ok = self.process_quiz(lecture, chapter_dir) is not False
                        elif clazz == "practice":
                            ok = self.process_practice(lecture, chapter_dir) is not False
                        else:
                            ok = self.process_role_play(lecture, chapter_dir)
                    except Exception:
                        self.logger.exception(f"    > Error processing {clazz}")
                        ok = False
                    if ok:
                        self.summary["downloaded"] += 1
                    else:
                        self.summary["failed"].append(f"{lecture_title} ({clazz})")
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
                    self.logger.info(
                        f"  > Processing lecture {index} of {total_lectures}"
                    )

                    # Check if the lecture is already downloaded
                    if lecture_path.is_file():
                        self.logger.info(
                            "      > Lecture '%s' is already downloaded, skipping..."
                            % lecture_title
                        )
                        self.summary["already_present"] += 1
                    else:
                        # Check if the file is an html file
                        if extension == "html":
                            # if the html content is None or an empty string, skip it so we dont save empty html files
                            if (
                                parsed_lecture.get("html_content") != None
                                and parsed_lecture.get("html_content") != ""
                            ):
                                html_content = (
                                    parsed_lecture.get("html_content")
                                    .encode("utf8", "ignore")
                                    .decode("utf8")
                                )
                                lecture_path = chapter_dir / "{}.html".format(
                                    sanitize_filename(lecture_title)
                                )
                                try:
                                    with lecture_path.open(
                                        mode="w", encoding="utf8"
                                    ) as f:
                                        f.write(html_content)
                                    self.summary["downloaded"] += 1
                                except Exception:
                                    self.logger.exception(
                                        "    > Failed to write html file"
                                    )
                                    self.summary["failed"].append(lecture_title)
                        elif self.process_lecture(
                            parsed_lecture, lecture_path, chapter_dir
                        ):
                            self.summary["downloaded"] += 1
                        else:
                            self.summary["failed"].append(lecture_title)

                # download subtitles for this lecture
                subtitles = parsed_lecture.get("subtitles")
                if (
                    self.download_captions
                    and subtitles != None
                    and lecture_extension == None
                ):
                    self.logger.info(
                        "Processing {} caption(s)...".format(len(subtitles))
                    )
                    for subtitle in subtitles:
                        lang = subtitle.get("language")
                        if lang == self.lang or self.lang == "all":
                            if not self.process_caption(
                                subtitle, lecture_title, chapter_dir
                            ):
                                self.summary["failed"].append(
                                    f"{lecture_title} (caption: {lang})"
                                )

                if self.download_assets:
                    assets = parsed_lecture.get("assets")
                    self.logger.info(
                        "    > Processing {} asset(s) for lecture...".format(
                            len(assets)
                        )
                    )

                    for asset in assets:
                        asset_type = asset.get("type")
                        file_path = asset.get("filename")
                        download_url = asset.get("download_url")

                        if asset_type == "article":
                            body = asset.get("body")
                            # stip the 03d prefix
                            lecture_path = os.path.join(
                                chapter_dir,
                                "{}.html".format(sanitize_filename(lecture_title)),
                            )
                            try:
                                template_path = Path(
                                    os.path.dirname(__file__),
                                    "templates",
                                    "article_template.html",
                                )
                                with open(template_path, "r") as f:
                                    content = f.read()
                                    content = content.replace(
                                        "__title_placeholder__", lecture_title[4:]
                                    )
                                    content = content.replace(
                                        "__data_placeholder__", body
                                    )
                                    with open(
                                        lecture_path, encoding="utf8", mode="w"
                                    ) as f:
                                        f.write(content)
                            except Exception as e:
                                self.logger.error(f"    > Failed to write html file: {e}")
                                continue
                        elif asset_type == "video":
                            self.logger.warning(
                                "If you're seeing this message, that means that you reached a secret area that I haven't finished! jk I haven't implemented handling for this asset type, please report this at https://github.com/Puyodead1/udemy-downloader/issues so I can add it. When reporting, please provide the following information: "
                            )
                            self.logger.warning("AssetType: Video; AssetData: %s", asset)
                        elif (
                            asset_type == "audio"
                            or asset_type == "e-book"
                            or asset_type == "file"
                            or asset_type == "presentation"
                            or asset_type == "ebook"
                            or asset_type == "source_code"
                        ):
                            try:
                                ret_code = download_aria(
                                    download_url, chapter_dir, file_path
                                )
                                self.logger.debug(
                                    f"      > Download return code: {ret_code}"
                                )
                            except Exception:
                                self.logger.exception("> Error downloading asset")
                                self.summary["failed"].append(
                                    f"{lecture_title} (asset: {file_path})"
                                )
                        elif asset_type == "external_link":
                            # write the external link to a shortcut file
                            file_path = chapter_dir / f"{file_path}.url"

                            with file_path.open(mode="w") as f:
                                f.write("[InternetShortcut]\n")
                                f.write(f"URL={download_url}")

                            # save all the external links to a single file
                            savedirs, name = os.path.split(
                                os.path.join(chapter_dir, file_path)
                            )
                            file_path = "external-links.txt"
                            file_path = Path(savedirs, file_path)
                            file_data = []
                            if file_path.is_file():
                                file_data = [
                                    i.strip().lower()
                                    for i in open(
                                        file_path, encoding="utf-8", errors="ignore"
                                    )
                                    if i
                                ]

                            content = "\n{}\n{}\n".format(name, download_url)
                            if name.lower() not in file_data:
                                with file_path.open(
                                    mode="a", encoding="utf-8", errors="ignore"
                                ) as f:
                                    f.write(content)


        self.log_summary()

    def log_summary(self):
        failed = self.summary["failed"]
        self.logger.info(
            "> Finished: %d downloaded, %d already present, %d failed",
            self.summary["downloaded"],
            self.summary["already_present"],
            len(failed),
        )
        if failed:
            self.logger.warning(
                "> These items failed, run the same command again to retry them:"
            )
            for item in failed:
                self.logger.warning(f"    - {item}")
            self.logger.warning(f"> Details are in the log file: {self.log_file_path}")
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

            for position, entry in enumerate(course, 1):
                clazz = entry.get("_class")

                if clazz == "chapter":
                    # reset lecture tracking
                    if not self.use_continuous_lecture_numbers:
                        lecture_counter = 0
                    lectures = []

                    chapter_index = entry.get("object_index")
                    chapter_title = "{0:02d} - ".format(
                        chapter_index
                    ) + sanitize_filename(entry.get("title"))

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
                elif clazz in ("lecture", "quiz", "practice", "role-play"):
                    lecture_counter += 1
                    lecture_id = entry.get("id")
                    if len(self.parsed_data["chapters"]) == 0:
                        # dummy chapters to handle lectures without chapters
                        chapter_index = entry.get("object_index")
                        chapter_title = "{0:02d} - ".format(
                            chapter_index
                        ) + sanitize_filename(entry.get("title"))
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
                        self.logger.debug(
                            f"Processing {position} of {len(course)}"
                        )

                        lecture_index = entry.get("object_index")
                        lecture_title = "{0:03d} ".format(
                            lecture_counter
                        ) + sanitize_filename(entry.get("title"))

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
                        self.logger.debug(f"{clazz.capitalize()}: ID is None, skipping")

                self.parsed_data["chapters"][chapter_index_counter][
                    "lectures"
                ] = lectures
                self.parsed_data["chapters"][chapter_index_counter]["lecture_count"] = (
                    len(lectures)
                )

            self.parsed_data["total_chapters"] = len(self.parsed_data["chapters"])
            self.parsed_data["total_lectures"] = sum(
                [
                    entry.get("lecture_count", 0)
                    for entry in self.parsed_data["chapters"]
                    if entry
                ]
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
                    source = min(
                        lecture_sources,
                        key=lambda x: abs(int(x.get("height")) - self.quality),
                    )
                self.logger.info(
                    f"      > Lecture '{lecture_title}' has DRM, attempting to download. Selected quality: {source.get('height')}"
                )
                return self.handle_segments(
                    source.get("download_url"),
                    source.get("format_id"),
                    str(lecture_id),
                    lecture_title,
                    lecture_path,
                    chapter_dir,
                )
            else:
                self.logger.info(
                    f"      > Lecture '{lecture_title}' is missing media links"
                )
                self.logger.debug(f"Lecture source count: {len(lecture_sources)}")
                return False
        else:
            sources = lecture.get("sources")
            sources = sorted(sources, key=lambda x: int(x.get("height")), reverse=True)
            if sources:
                if not os.path.isfile(lecture_path):
                    self.logger.info(
                        "      > Lecture doesn't have DRM, attempting to download..."
                    )
                    source = sources[0]  # first index is the best quality
                    if isinstance(self.quality, int):
                        source = min(
                            sources,
                            key=lambda x: abs(int(x.get("height")) - self.quality),
                        )
                    try:
                        self.logger.info(
                            "      ====== Selected quality: %s %s",
                            source.get("type"),
                            source.get("height"),
                        )
                        url = source.get("download_url")
                        source_type = source.get("type")
                        if source_type == "hls":
                            temp_filepath = str(lecture_path).replace(
                                ".mp4", ".%(ext)s"
                            )
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
                                    codec = (
                                        "hevc_nvenc" if self.use_nvenc else "libx265"
                                    )
                                    transcode = (
                                        "-hwaccel cuda -hwaccel_output_format cuda".split(
                                            " "
                                        )
                                        if self.use_nvenc
                                        else []
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
                                        "-metadata",
                                        "comment=Downloaded with Udemy-Downloader by Puyodead1 (https://github.com/Puyodead1/udemy-downloader)",
                                        tmp_file_path,
                                    ]
                                    self.logger.debug(" ".join([str(x) for x in cmd]))
                                    process = subprocess.Popen(cmd)
                                    log_subprocess_output(
                                        "FFMPEG-STDOUT", process.stdout
                                    )
                                    log_subprocess_output(
                                        "FFMPEG-STDERR", process.stderr
                                    )
                                    ret_code = process.wait()
                                    if ret_code == 0:
                                        os.unlink(lecture_path)
                                        os.rename(tmp_file_path, lecture_path)
                                        self.logger.info("      > Encoding complete")
                                    else:
                                        # the unencoded download is kept, so the lecture still counts as downloaded
                                        self.logger.error(
                                            "      > Encoding returned non-zero return code"
                                        )
                                return True
                            self.logger.error(
                                f"      > HLS download failed with return code {ret_code}"
                            )
                            return False
                        else:
                            ret_code = download_aria(
                                url, chapter_dir, lecture_path.name
                            )
                            self.logger.debug(
                                f"      > Download return code: {ret_code}"
                            )
                            return True
                    except Exception:
                        self.logger.exception(">        Error downloading lecture")
                        return False
                else:
                    self.logger.info(
                        f"      > Lecture '{lecture_title}' is already downloaded, skipping..."
                    )
                    return True
            else:
                self.logger.error("      > Missing sources for lecture %s", lecture.get("lecture_title"))
                return False

    def handle_segments(
        self,
        url: str,
        format_id,
        lecture_id: str,
        video_title: str,
        output_path: Path,
        chapter_dir: Path,
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
            self.logger.warning(
                "Return code from the downloader was non-0 (error), skipping!"
            )
            os.chdir(self.home_dir)
            return False

        pssh = extract_pssh(video_filepath_enc)
        if pssh is None or not pssh.key_ids:
            self.logger.error("No Widevine PSSH found in the video track, skipping!")
            os.chdir(self.home_dir)
            return False
        kid = pssh.key_ids[0]

        self.logger.debug(f"KID is: {kid.hex}")
        self.logger.debug(f"PSSH is: {pssh}")

        key = None

        if kid is not None:
            try:
                key = self.keys[kid.hex.replace("-", "")]
            except KeyError:
                pass

        if not key and not self.device:
            self.logger.error(
                "No key found and no device is available to make a license request, skipping!"
            )
            os.chdir(self.home_dir)
            return False

        if not key:
            # request a media license token
            lecture_url = LECTURE_URL.format(
                portal_name=self.portal_name,
                course_id=self.course_id,
                lecture_id=lecture_id,
                rand=random.random(),
            )
            self.logger.debug("Requesting a media license token...")
            try:
                r = self.session._get(lecture_url)
                r.raise_for_status()
                media_license_token = r.json()["asset"]["media_license_token"]
            except Exception as e:
                self.logger.error(f"Failed to get media license token: {e}")
                os.chdir(self.home_dir)
                return False

            # try to make a license request
            license_url = LICENSE_URL.format(
                portal_name=self.portal_name, auth_token=media_license_token
            )
            session_id = self.cdm.open()
            try:
                challenge = self.cdm.get_license_challenge(
                    session_id, pssh, "STREAMING", False
                )
                self.logger.debug(f"Making license request to {license_url}")
                r = self.session._post(license_url, challenge)
                self.cdm.parse_license(session_id, r.content)
                keys = self.cdm.get_keys(session_id, "CONTENT")
                # find key that matches kid
                key = next((k.key.hex() for k in keys if k.kid == kid), None)
            except Exception as e:
                self.logger.error(f"Failed to get license: {e}")
            finally:
                self.cdm.close(session_id)

            if not key:
                self.logger.error("Failed to get decryption key, skipping!")
                os.chdir(self.home_dir)
                return False

            self.keys[kid.hex.replace("-", "")] = key
            self.save_keys()

            self.logger.debug(f"Got decryption key: {key}")

        try:
            # some audio tracks have an empty saiz box that ffmpeg refuses to open (#307, #314)
            fixed = fix_empty_saiz(audio_filepath_enc)
            if fixed:
                self.logger.debug(f"> Removed {fixed} empty saiz/saio boxes from the audio track")
            self.logger.info("> Merging video and audio, this might take a minute...")
            self.mux_process(
                video_filepath_enc,
                audio_filepath_enc,
                video_title,
                temp_output_path,
                key,
            )
            self.logger.debug("> Merging complete, renaming final file...")
            temp_output_path.rename(output_path)
            self.logger.debug("> Cleaning up temporary files...")
            os.remove(video_filepath_enc)
            os.remove(audio_filepath_enc)
            return True
        except Exception as e:
            self.logger.exception(f"Muxing error: {e}")
            return False
        finally:
            os.chdir(self.home_dir)
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
        key: Union[str | None] = None,
    ):
        codec = "hevc_nvenc" if self.use_nvenc else "libx265"
        transcode = (
            ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
            if self.use_nvenc
            else []
        )
        decryption_arg = ["-decryption_key", key] if key is not None else []

        # build an argument list instead of a shell string so titles can't inject commands
        command = [] if os.name == "nt" else ["nice", "-n", "7"]
        command += ["ffmpeg"]
        if self.use_h265:
            command += transcode
        command += ["-y", *decryption_arg, "-i", str(video_filepath)]
        command += [*decryption_arg, "-i", str(audio_filepath)]
        if self.use_h265:
            command += [
                "-c:v",
                codec,
                "-vtag",
                "hvc1",
                "-crf",
                str(self.h265_crf),
                "-preset",
                self.h265_preset,
                "-c:a",
                "copy",
            ]
        else:
            command += ["-c", "copy"]
        command += [
            "-fflags",
            "+bitexact",
            "-shortest",
            "-map_metadata",
            "-1",
            "-metadata",
            f"title={video_title}",
            "-metadata",
            "comment=Downloaded with Udemy-Downloader by Puyodead1 (https://github.com/Puyodead1/udemy-downloader)",
            str(output_path),
        ]

        self.logger.debug(" ".join(command))
        process = subprocess.Popen(command)
        log_subprocess_output("FFMPEG-STDOUT", process.stdout)
        log_subprocess_output("FFMPEG-STDERR", process.stderr)
        ret_code = process.wait()
        if ret_code != 0:
            raise Exception("Muxing returned a non-zero exit code")

        return ret_code

    def process_caption(self, caption, lecture_title: str, lecture_dir: Path, tries=0):
        filename = "%s_%s.%s" % (
            sanitize_filename(lecture_title),
            caption.get("language"),
            caption.get("extension"),
        )
        filename_no_ext = "%s_%s" % (
            sanitize_filename(lecture_title),
            caption.get("language"),
        )
        filepath = lecture_dir / filename
        srt_filepath = lecture_dir / f"{filename_no_ext}.srt"
        is_vtt = caption.get("extension") == "vtt"

        # vtt captions are converted to srt (and the vtt removed unless --keep-vtt), so check for either
        if filepath.is_file() or (is_vtt and srt_filepath.is_file()):
            self.logger.info("    > Caption '%s' already downloaded." % filename)
            return True
        else:
            self.logger.info("    >  Downloading caption: '%s'" % filename)
            try:
                ret_code = download_aria(
                    caption.get("download_url"), lecture_dir, filename
                )
                self.logger.debug(f"      > Download return code: {ret_code}")
            except Exception as e:
                if tries >= 3:
                    self.logger.error(
                        f"    > Error downloading caption: {e}. Exceeded retries, skipping."
                    )
                    return False
                else:
                    self.logger.error(
                        f"    > Error downloading caption: {e}. Will retry {3-tries} more times."
                    )
                    return self.process_caption(
                        caption, lecture_title, lecture_dir, tries + 1
                    )
            if is_vtt:
                try:
                    self.logger.debug("    > Converting caption to SRT format...")
                    convert(lecture_dir, filename_no_ext)
                    self.logger.debug("    > Caption conversion complete.")
                    if not self.keep_vtt:
                        filepath.unlink()
                except Exception:
                    self.logger.exception("    > Error converting caption")
                    return False
            return True

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
        template_path = Path(
            os.path.dirname(__file__), "templates", "quiz_template.html"
        )
        with open(template_path, "r", encoding="utf8") as f:
            page = f.read()
        quiz_data = {
            "id": lecture["data"].get("id"),
            "title": lecture["data"].get("title"),
            "description": lecture["data"].get("description"),
            "pass_score": lecture["data"].get("pass_percent"),
            "assessments": quiz["contents"],
        }
        page = page.replace("%%TITLE%%", html.escape(lecture["data"].get("title") or ""))
        page = page.replace("%%QUIZ_JSON%%", self._json_for_script(quiz_data))
        with lecture_path.open(mode="w", encoding="utf8") as f:
            f.write(page)

    def process_coding_assignment(self, quiz, lecture, chapter_dir: Path):
        lecture_title = lecture.get("lecture_title")
        lecture_index = lecture.get("lecture_index")
        lecture_file_name = sanitize_filename(lecture_title + ".html")
        lecture_path = chapter_dir / lecture_file_name

        self.logger.info(f"  > Processing quiz {lecture_index} (coding assignment)")

        self._write_template(
            "coding_assignment_template.html",
            {
                "title": lecture_title,
                "hasInstructions": quiz["hasInstructions"],
                "hasTests": quiz["hasTests"],
                "hasSolutions": quiz["hasSolutions"],
                "instructions": quiz["contents"]["instructions"],
                "tests": quiz["contents"]["tests"],
                "solutions": quiz["contents"]["solutions"],
            },
            lecture_path,
        )

    @staticmethod
    def _json_for_script(data):
        # escape "</" so a value containing "</script>" can't end the script tag early
        return json.dumps(data).replace("</", "<\\/")

    def _write_template(self, template_name: str, data, lecture_path: Path):
        template_path = Path(os.path.dirname(__file__), "templates", template_name)
        page = template_path.read_text(encoding="utf8")
        page = page.replace("__data_placeholder__", self._json_for_script(data))
        lecture_path.write_text(page, encoding="utf8")

    def process_practice(self, lecture, chapter_dir: Path):
        practice = self._get_practice_with_info(lecture.get("id"))

        lecture_title = lecture.get("lecture_title")
        lecture_counter = lecture.get("index")
        lecture_path = chapter_dir / sanitize_filename(lecture_title + ".html")

        self.logger.info(f"  > Processing practice {lecture.get('lecture_index')}")

        components = practice.get("instructions", []) + practice.get("solutions", [])
        for component in components:
            asset = component.get("asset")
            if asset and lecture_counter:
                asset["title"] = "{0:03d} {1}".format(lecture_counter, asset.get("title"))

        if self.download_assets:
            for component in components:
                asset = component.get("asset")
                if asset:
                    self._download_practice_asset(lecture, asset, chapter_dir)

        self._write_template(
            "assignment_template.html",
            {
                "title": lecture_title,
                "description": practice.get("description"),
                "estimated_duration": practice.get("estimated_duration"),
                "instructions": practice.get("instructions"),
                "solutions": practice.get("solutions"),
                "questions": practice.get("questions"),
            },
            lecture_path,
        )

    def _download_practice_asset(self, lecture, asset: dict, chapter_dir: Path):
        asset_id = asset.get("id")
        filename = sanitize_filename(asset.get("title"))
        try:
            if (asset.get("asset_type") or "").lower() == "video":
                # video assets come from the assets api instead of the practice's supplementary assets
                url = PRACTICE_VIDEO_ASSET_URL.format(
                    portal_name=self.portal_name, asset_id=asset_id
                )
                media_sources = self._get_json(url).get("media_sources") or []
                mp4_sources = [
                    source
                    for source in media_sources
                    if source.get("type") == "video/mp4" and source.get("src")
                ]
                if not mp4_sources:
                    self.logger.warning(
                        f"    > No MP4 sources found for practice video asset {asset_id}"
                    )
                    return
                best = max(mp4_sources, key=lambda x: int(x.get("label") or 0))
                if not filename.lower().endswith(".mp4"):
                    filename += ".mp4"
                download_url = best.get("src")
            else:
                url = PRACTICE_SUPPLEMENTARY_ASSET_URL.format(
                    portal_name=self.portal_name,
                    practice_id=lecture.get("id"),
                    asset_id=asset_id,
                )
                files = (self._get_json(url).get("download_urls") or {}).get("File")
                if not files:
                    self.logger.warning(
                        f"    > No download link found for practice asset {asset_id}"
                    )
                    return
                download_url = files[0].get("file")

            if (chapter_dir / filename).is_file():
                self.logger.info(f"    > Practice asset '{filename}' already downloaded")
                return
            ret_code = download_aria(download_url, chapter_dir, filename)
            self.logger.debug(f"      > Download return code: {ret_code}")
        except Exception:
            self.logger.exception("    > Error downloading practice asset")
            self.summary["failed"].append(
                f"{lecture.get('lecture_title')} (practice asset: {filename})"
            )

    def process_role_play(self, lecture, chapter_dir: Path):
        lecture_title = lecture.get("lecture_title")
        lecture_index = lecture.get("lecture_index")
        lecture_path = chapter_dir / sanitize_filename(lecture_title + ".html")

        self.logger.info(f"  > Processing role play {lecture_index}")

        # the role play is only available in the course page, which needs the access_token cookie
        cookies = self.session._session.cookies
        if self.bearer_token and not cookies.get("access_token"):
            cookies.set("access_token", self.bearer_token, domain="www.udemy.com")

        url = ROLE_PLAY_URL.format(
            portal_name=self.portal_name, course_name="None", role_play_id=lecture.get("id")
        )
        role_play = extract_role_play(self.session._get(url).text)
        if not role_play:
            self.logger.warning(f"  > Could not extract role play for {lecture_index}.")
            return False

        meeting = role_play.get("meeting") or {}
        character = role_play.get("aiCharacter") or {}
        self._write_template(
            "role_play_template.html",
            {
                "title": lecture_title,
                "scenario": role_play.get("scenario", ""),
                "learnerRole": role_play.get("learnerRole", ""),
                "meeting": {
                    "title": meeting.get("title", ""),
                    "goalsList": meeting.get("goalsList", []),
                },
                "aiCharacter": {
                    "name": character.get("name", ""),
                    "role": character.get("role", ""),
                    "details": character.get("details", ""),
                },
            },
            lecture_path,
        )
        return True

    def load_keys(self):
        if self.key_file_path.exists():
            with self.key_file_path.open("r") as keyfile:
                self.keys = json.loads(keyfile.read())
        elif not self.device:
            # with a device, keys are requested at runtime so a missing keyfile is expected
            self.logger.warning(
                "> Keyfile not found, you may not be able to decrypt DRM content."
            )

    def save_keys(self):
        self.logger.debug("> Saving keys to keyfile...")
        with self.key_file_path.open("w") as keyfile:
            keyfile.write(json.dumps(self.keys))
