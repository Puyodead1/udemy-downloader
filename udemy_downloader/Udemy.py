"""
This file was modified from udemy-dl
https://github.com/r0oth3x49/udemy-dl/

Copyright (c) 2018-2025 Nasir Khan (r0ot h3x49)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the
Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, 
and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR
ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH 
THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import time
import sys
import m3u8
import yt_dlp
import re
from requests.exceptions import ConnectionError as conn_error
from UdemyAuth import UdemyAuth
from utils import _clean
from constants import COURSE_SEARCH, COURSE_URL, MY_COURSES_URL, COLLECTION_URL

class Udemy:
    def __init__(self, access_token):
        self.session = None
        self.access_token = None
        self.auth = UdemyAuth(cache_session=False)
        if not self.session:
            self.session, self.access_token = self.auth.authenticate(
                access_token=access_token)

        if self.session and self.access_token:
            self.session._headers.update(
                {"Authorization": "Bearer {}".format(self.access_token)})
            self.session._headers.update({
                "X-Udemy-Authorization":
                "Bearer {}".format(self.access_token)
            })
            print("Login Success")
        else:
            print("Login Failure!")
            sys.exit(1)

    def _extract_supplementary_assets(self, supp_assets):
        _temp = []
        for entry in supp_assets:
            title = _clean(entry.get("title"))
            filename = entry.get("filename")
            download_urls = entry.get("download_urls")
            external_url = entry.get("external_url")
            asset_type = entry.get("asset_type").lower()
            id = entry.get("id")
            if asset_type == "file":
                if download_urls and isinstance(download_urls, dict):
                    extension = filename.rsplit(
                        ".", 1)[-1] if "." in filename else ""
                    download_url = download_urls.get("File", [])[0].get("file")
                    _temp.append({
                        "type": "file",
                        "title": title,
                        "filename": filename,
                        "extension": extension,
                        "download_url": download_url,
                        "id": id
                    })
            elif asset_type == "sourcecode":
                if download_urls and isinstance(download_urls, dict):
                    extension = filename.rsplit(
                        ".", 1)[-1] if "." in filename else ""
                    download_url = download_urls.get("SourceCode",
                                                     [])[0].get("file")
                    _temp.append({
                        "type": "source_code",
                        "title": title,
                        "filename": filename,
                        "extension": extension,
                        "download_url": download_url,
                        "id": id
                    })
            elif asset_type == "externallink":
                _temp.append({
                    "type": "external_link",
                    "title": title,
                    "filename": filename,
                    "extension": "txt",
                    "download_url": external_url,
                    "id": id
                })
        return _temp

    def _extract_ppt(self, asset):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("Presentation", [])[0].get("file")
            _temp.append({
                "type": "presentation",
                "filename": filename,
                "extension": extension,
                "download_url": download_url,
                "id": id
            })
        return _temp

    def _extract_file(self, asset):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("File", [])[0].get("file")
            _temp.append({
                "type": "file",
                "filename": filename,
                "extension": extension,
                "download_url": download_url,
                "id": id
            })
        return _temp

    def _extract_ebook(self, asset):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("E-Book", [])[0].get("file")
            _temp.append({
                "type": "ebook",
                "filename": filename,
                "extension": extension,
                "download_url": download_url,
                "id": id
            })
        return _temp

    def _extract_audio(self, asset):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("Audio", [])[0].get("file")
            _temp.append({
                "type": "audio",
                "filename": filename,
                "extension": extension,
                "download_url": download_url,
                "id": id
            })
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
                if (source.get("type") == "application/x-mpegURL"
                        or "m3u8" in download_url):
                    if not skip_hls:
                        out = self._extract_m3u8(download_url)
                        if out:
                            _temp.extend(out)
                else:
                    _type = source.get("type")
                    _temp.append({
                        "type": "video",
                        "height": height,
                        "width": width,
                        "extension": _type.replace("video/", ""),
                        "download_url": download_url,
                    })
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
                lang = (track.get("language") or track.get("srclang")
                        or track.get("label")
                        or track["locale_id"].split("_")[0])
                ext = "vtt" if "vtt" in download_url.rsplit(".",
                                                            1)[-1] else "srt"
                _temp.append({
                    "type": "subtitle",
                    "language": lang,
                    "extension": ext,
                    "download_url": download_url,
                })
        return _temp

    def _extract_m3u8(self, url):
        """extracts m3u8 streams"""
        _temp = []
        try:
            resp = self.session._get(url)
            resp.raise_for_status()
            raw_data = resp.text
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
                download_url = pl.uri
                if height not in seen:
                    seen.add(height)
                    _temp.append({
                        "type": "hls",
                        "height": height,
                        "width": width,
                        "extension": "mp4",
                        "download_url": download_url,
                    })
        except Exception as error:
            print(f"Udemy Says : '{error}' while fetching hls streams..")
        return _temp

    def _extract_mpd(self, url):
        """extracts mpd streams"""
        _temp = []
        try:
            ytdl = yt_dlp.YoutubeDL({
                'quiet': True,
                'no_warnings': True,
                "allow_unplayable_formats": True
            })
            results = ytdl.extract_info(url,
                                        download=False,
                                        force_generic_extractor=True)
            seen = set()
            formats = results.get("formats")

            format_id = results.get("format_id")
            best_audio_format_id = format_id.split("+")[1]
            best_audio = next((x for x in formats
                               if x.get("format_id") == best_audio_format_id),
                              None)
            for f in formats:
                if "video" in f.get("format_note"):
                    # is a video stream
                    format_id = f.get("format_id")
                    extension = f.get("ext")
                    height = f.get("height")
                    width = f.get("width")

                    if height and height not in seen:
                        seen.add(height)
                        _temp.append({
                            "type": "dash",
                            "height": str(height),
                            "width": str(width),
                            "format_id": f"{format_id},{best_audio_format_id}",
                            "extension": extension,
                            "download_url": f.get("manifest_url")
                        })
                else:
                    # unknown format type
                    continue
        except Exception as error:
            print(f"Error fetching MPD streams: '{error}'")
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

    def _subscribed_courses(self, portal_name, course_name):
        results = []
        self.session._headers.update({
            "Host":
            "{portal_name}.udemy.com".format(portal_name=portal_name),
            "Referer":
            "https://{portal_name}.udemy.com/home/my-courses/search/?q={course_name}"
            .format(portal_name=portal_name, course_name=course_name),
        })
        url = COURSE_SEARCH.format(portal_name=portal_name,
                                   course_name=course_name)
        try:
            webpage = self.session._get(url).json()
        except conn_error as error:
            print(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(0)
        except (ValueError, Exception) as error:
            print(f"Udemy Says: {error} on {url}")
            time.sleep(0.8)
            sys.exit(0)
        else:
            results = webpage.get("results", [])
        return results

    def _extract_course_json(self, url, course_id, portal_name):
        self.session._headers.update({"Referer": url})
        url = COURSE_URL.format(portal_name=portal_name, course_id=course_id)
        try:
            resp = self.session._get(url)
            if resp.status_code in [502, 503]:
                print(
                    "> The course content is large, using large content extractor..."
                )
                resp = self._extract_large_course_content(url=url)
            else:
                resp = resp.json()
        except conn_error as error:
            print(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(0)
        except (ValueError, Exception):
            resp = self._extract_large_course_content(url=url)
            return resp
        else:
            return resp

    def _extract_large_course_content(self, url):
        url = url.replace("10000", "50") if url.endswith("10000") else url
        try:
            data = self.session._get(url).json()
        except conn_error as error:
            print(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(0)
        else:
            _next = data.get("next")
            while _next:
                print("Downloading course information.. ")
                try:
                    resp = self.session._get(_next).json()
                except conn_error as error:
                    print(f"Udemy Says: Connection error, {error}")
                    time.sleep(0.8)
                    sys.exit(0)
                else:
                    _next = resp.get("next")
                    results = resp.get("results")
                    if results and isinstance(results, list):
                        for d in resp["results"]:
                            data["results"].append(d)
            return data

    def __extract_course(self, response, course_name):
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
            print(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(0)
        except (ValueError, Exception) as error:
            print(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(0)
        else:
            results = webpage.get("results", [])
        return results

    def _subscribed_collection_courses(self, portal_name):
        url = COLLECTION_URL.format(portal_name=portal_name)
        courses_lists = []
        try:
            webpage = self.session._get(url).json()
        except conn_error as error:
            print(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(0)
        except (ValueError, Exception) as error:
            print(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(0)
        else:
            results = webpage.get("results", [])
            if results:
                [
                    courses_lists.extend(courses.get("courses", []))
                    for courses in results if courses.get("courses", [])
                ]
        return courses_lists

    def _archived_courses(self, portal_name):
        results = []
        try:
            url = MY_COURSES_URL.format(portal_name=portal_name)
            url = f"{url}&is_archived=true"
            webpage = self.session._get(url).json()
        except conn_error as error:
            print(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(0)
        except (ValueError, Exception) as error:
            print(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(0)
        else:
            results = webpage.get("results", [])
        return results

    def _my_courses(self, portal_name):
        results = []
        try:
            url = MY_COURSES_URL.format(portal_name=portal_name)
            webpage = self.session._get(url).json()
        except conn_error as error:
            print(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(0)
        except (ValueError, Exception) as error:
            print(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(0)
        else:
            results = webpage.get("results", [])
        return results

    def _subscribed_collection_courses(self, portal_name):
        url = COLLECTION_URL.format(portal_name=portal_name)
        courses_lists = []
        try:
            webpage = self.session._get(url).json()
        except conn_error as error:
            print(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(0)
        except (ValueError, Exception) as error:
            print(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(0)
        else:
            results = webpage.get("results", [])
            if results:
                [
                    courses_lists.extend(courses.get("courses", []))
                    for courses in results if courses.get("courses", [])
                ]
        return courses_lists

    def _archived_courses(self, portal_name):
        results = []
        try:
            url = MY_COURSES_URL.format(portal_name=portal_name)
            url = f"{url}&is_archived=true"
            webpage = self.session._get(url).json()
        except conn_error as error:
            print(f"Udemy Says: Connection error, {error}")
            time.sleep(0.8)
            sys.exit(0)
        except (ValueError, Exception) as error:
            print(f"Udemy Says: {error}")
            time.sleep(0.8)
            sys.exit(0)
        else:
            results = webpage.get("results", [])
        return results

    def _extract_course_info(self, url):
        portal_name, course_name = self.extract_course_name(url)
        course = {}
        results = self._subscribed_courses(portal_name=portal_name,
                                           course_name=course_name)
        course = self.__extract_course(response=results,
                                       course_name=course_name)
        if not course:
            results = self._my_courses(portal_name=portal_name)
            course = self.__extract_course(response=results,
                                           course_name=course_name)
        if not course:
            results = self._subscribed_collection_courses(
                portal_name=portal_name)
            course = self.__extract_course(response=results,
                                           course_name=course_name)
        if not course:
            results = self._archived_courses(portal_name=portal_name)
            course = self.__extract_course(response=results,
                                           course_name=course_name)

        if course:
            course.update({"portal_name": portal_name})
            return course
        if not course:
            print("Downloading course information, course id not found .. ")
            print(
                "It seems either you are not enrolled or you have to visit the course atleast once while you are logged in.",
            )
            print("Trying to logout now...", )
            self.session.terminate()
            print("Logged out successfully.", )
            sys.exit(0)