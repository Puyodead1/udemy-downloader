import os
import requests
import json
import glob
import argparse
import sys
import re
import time
import asyncio
import json
import cloudscraper
import m3u8
from tqdm import tqdm
from dotenv import load_dotenv
from mpegdash.parser import MPEGDASHParser
from utils import extract_kid
from vtt_to_srt import convert
from requests.exceptions import ConnectionError as conn_error
from html.parser import HTMLParser as compat_HTMLParser
from sanitize import sanitize, slugify, SLUG_OK
import subprocess
import yt_dlp

download_dir = os.path.join(os.getcwd(), "out_dir")
working_dir = os.path.join(os.getcwd(), "working_dir")
keyfile_path = os.path.join(os.getcwd(), "keyfile.json")
retry = 3
downloader = None
HEADERS = {
    "Origin": "www.udemy.com",
    "User-Agent":
    "Mozilla/5.0 (Windows NT 6.3; Win64; x64; rv:85.0) Gecko/20100101 Firefox/85.0",
    "Accept": "*/*",
    "Accept-Encoding": None,
}
LOGIN_URL = "https://www.udemy.com/join/login-popup/?ref=&display_type=popup&loc"
LOGOUT_URL = "https://www.udemy.com/user/logout"
COURSE_URL = "https://{portal_name}.udemy.com/api-2.0/courses/{course_id}/cached-subscriber-curriculum-items?fields[asset]=results,title,external_url,time_estimation,download_urls,slide_urls,filename,asset_type,captions,media_license_token,course_is_drmed,media_sources,stream_urls,body&fields[chapter]=object_index,title,sort_order&fields[lecture]=id,title,object_index,asset,supplementary_assets,view_html&page_size=10000"
COURSE_SEARCH = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses?fields[course]=id,url,title,published_title&page=1&page_size=500&search={course_name}"
SUBSCRIBED_COURSES = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses/?ordering=-last_accessed&fields[course]=id,title,url&page=1&page_size=12"
MY_COURSES_URL = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses?fields[course]=id,url,title,published_title&ordering=-last_accessed,-access_time&page=1&page_size=10000"
COLLECTION_URL = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses-collections/?collection_has_courses=True&course_limit=20&fields[course]=last_accessed_time,title,published_title&fields[user_has_subscribed_courses_collection]=@all&page=1&page_size=1000"


def _clean(text):
    ok = re.compile(r'[^\\/:*?"<>|]')
    text = "".join(x if ok.match(x) else "_" for x in text)
    text = re.sub(r"\.+$", "", text.strip())
    return text


def _sanitize(self, unsafetext):
    text = sanitize(
        slugify(unsafetext, lower=False, spaces=True, ok=SLUG_OK + "().[]"))
    return text


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

    def _extract_ppt(self, assets):
        _temp = []
        download_urls = assets.get("download_urls")
        filename = assets.get("filename")
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

    def _extract_file(self, assets):
        _temp = []
        download_urls = assets.get("download_urls")
        filename = assets.get("filename")
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

    def _extract_ebook(self, assets):
        _temp = []
        download_urls = assets.get("download_urls")
        filename = assets.get("filename")
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

    def _extract_audio(self, assets):
        _temp = []
        download_urls = assets.get("download_urls")
        filename = assets.get("filename")
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
            return course.get("id"), course
        if not course:
            print("Downloading course information, course id not found .. ")
            print(
                "It seems either you are not enrolled or you have to visit the course atleast once while you are logged in.",
            )
            print("Trying to logout now...", )
            self.session.terminate()
            print("Logged out successfully.", )
            sys.exit(0)


class Session(object):
    def __init__(self):
        self._headers = HEADERS
        self._session = requests.sessions.Session()

    def _set_auth_headers(self, access_token="", client_id=""):
        self._headers["Authorization"] = "Bearer {}".format(access_token)
        self._headers["X-Udemy-Authorization"] = "Bearer {}".format(
            access_token)

    def _get(self, url):
        session = self._session.get(url, headers=self._headers)
        if session.ok or session.status_code in [502, 503]:
            return session
        if not session.ok:
            raise Exception(f"{session.status_code} {session.reason}")

    def _post(self, url, data, redirect=True):
        session = self._session.post(url,
                                     data,
                                     headers=self._headers,
                                     allow_redirects=redirect)
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


def search_regex(pattern,
                 string,
                 name,
                 default=object(),
                 fatal=True,
                 flags=0,
                 group=None):
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
        print("[-] Unable to extract %s" % _name)
        exit(0)
    else:
        print("[-] unable to extract %s" % _name)
        exit(0)


class UdemyAuth(object):
    def __init__(self, username="", password="", cache_session=False):
        self.username = username
        self.password = password
        self._cache = cache_session
        self._session = Session()
        self._cloudsc = cloudscraper.create_scraper()

    def _form_hidden_input(self, form_id):
        try:
            resp = self._cloudsc.get(LOGIN_URL)
            resp.raise_for_status()
            webpage = resp.text
        except conn_error as error:
            raise error
        else:
            login_form = hidden_inputs(
                search_regex(
                    r'(?is)<form[^>]+?id=(["\'])%s\1[^>]*>(?P<form>.+?)</form>'
                    % form_id,
                    webpage,
                    "%s form" % form_id,
                    group="form",
                ))
            login_form.update({
                "email": self.username,
                "password": self.password
            })
            return login_form

    def authenticate(self, access_token="", client_id=""):
        if not access_token and not client_id:
            data = self._form_hidden_input(form_id="login-form")
            self._cloudsc.headers.update({"Referer": LOGIN_URL})
            auth_response = self._cloudsc.post(LOGIN_URL,
                                               data=data,
                                               allow_redirects=False)
            auth_cookies = auth_response.cookies

            access_token = auth_cookies.get("access_token", "")
            client_id = auth_cookies.get("client_id", "")

        if access_token:
            # dump cookies to configs
            # if self._cache:
            #     _ = to_configs(
            #         username=self.username,
            #         password=self.password,
            #         cookies=f"access_token={access_token}",
            #     )
            self._session._set_auth_headers(access_token=access_token,
                                            client_id=client_id)
            self._session._session.cookies.update(
                {"access_token": access_token})
            return self._session, access_token
        else:
            self._session._set_auth_headers()
            return None, None


if not os.path.exists(working_dir):
    os.makedirs(working_dir)

if not os.path.exists(download_dir):
    os.makedirs(download_dir)

# Get the keys
with open(keyfile_path, 'r') as keyfile:
    keyfile = keyfile.read()
keyfile = json.loads(keyfile)


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


def mux_process(video_title, video_filepath, audio_filepath, output_path):
    """
    @author Jayapraveen
    """
    if os.name == "nt":
        command = "ffmpeg -y -i \"{}\" -i \"{}\" -acodec copy -vcodec copy -fflags +bitexact -map_metadata -1 -metadata title=\"{}\" \"{}\"".format(
            video_filepath, audio_filepath, video_title, output_path)
    else:
        command = "nice -n 7 ffmpeg -y -i \"{}\" -i \"{}\" -acodec copy -vcodec copy -fflags +bitexact -map_metadata -1 -metadata title=\"{}\" \"{}\"".format(
            video_filepath, audio_filepath, video_title, output_path)
    os.system(command)


def decrypt(kid, in_filepath, out_filepath):
    """
    @author Jayapraveen
    """
    print("> Decrypting, this might take a minute...")
    try:
        key = keyfile[kid.lower()]
        if (os.name == "nt"):
            os.system(f"mp4decrypt --key 1:%s \"%s\" \"%s\"" %
                      (key, in_filepath, out_filepath))
        else:
            os.system(f"nice -n 7 mp4decrypt --key 1:%s \"%s\" \"%s\"" %
                      (key, in_filepath, out_filepath))
        print("> Decryption complete")
    except KeyError:
        raise KeyError("Key not found")


def handle_segments(url, format_id, video_title, lecture_working_dir,
                    output_path, concurrent_connections):
    temp_filepath = output_path.replace("%", "").replace(".mp4", "")
    temp_filepath = temp_filepath + ".mpd-part"
    video_filepath_enc = temp_filepath + ".mp4"
    audio_filepath_enc = temp_filepath + ".m4a"
    video_filepath_dec = temp_filepath + ".decrypted.mp4"
    audio_filepath_dec = temp_filepath + ".decrypted.m4a"
    print("> Downloading Lecture Tracks...")
    ret_code = subprocess.Popen([
        "yt-dlp", "--force-generic-extractor", "--allow-unplayable-formats",
        "--concurrent-fragments", f"{concurrent_connections}", "--downloader",
        "aria2c", "--fixup", "never", "-k", "-o", f"{temp_filepath}.%(ext)s",
        "-f", format_id, f"{url}"
    ]).wait()
    print("> Lecture Tracks Downloaded")

    print("Return code: " + str(ret_code))

    video_kid = extract_kid(video_filepath_enc)
    print("KID for video file is: " + video_kid)

    audio_kid = extract_kid(audio_filepath_enc)
    print("KID for audio file is: " + audio_kid)

    try:
        decrypt(video_kid, video_filepath_enc, video_filepath_dec)
        decrypt(audio_kid, audio_filepath_enc, audio_filepath_dec)
        mux_process(video_title, video_filepath_dec, audio_filepath_dec,
                    output_path)
        os.remove(video_filepath_enc)
        os.remove(audio_filepath_enc)
        os.remove(video_filepath_dec)
        os.remove(audio_filepath_dec)
    except Exception as e:
        print(f"Error: ", e)


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


def process_lecture(lecture, lecture_path, lecture_dir, quality, access_token,
                    concurrent_connections):
    lecture_title = lecture.get("lecture_title")
    is_encrypted = lecture.get("is_encrypted")
    lecture_sources = lecture.get("video_sources")

    if is_encrypted:
        if len(lecture_sources) > 0:
            lecture_working_dir = os.path.join(working_dir,
                                               str(lecture.get("asset_id")))

            if not os.path.isfile(lecture_path):
                source = lecture_sources[-1]  # last index is the best quality
                if isinstance(quality, int):
                    source = min(
                        lecture_sources,
                        key=lambda x: abs(int(x.get("height")) - quality))
                if not os.path.exists(lecture_working_dir):
                    os.mkdir(lecture_working_dir)
                print(f"      > Lecture '%s' has DRM, attempting to download" %
                      lecture_title)
                handle_segments(source.get("download_url"),
                                source.get("format_id"), lecture_title,
                                lecture_working_dir, lecture_path,
                                concurrent_connections)
            else:
                print(
                    "      > Lecture '%s' is already downloaded, skipping..." %
                    lecture_title)
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
            lecture_working_dir = os.path.join(working_dir,
                                               str(lecture.get("asset_id")))
            if not os.path.exists(lecture_working_dir):
                os.mkdir(lecture_working_dir)
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
                        temp_filepath = lecture_path.replace(".mp4", "")
                        temp_filepath = temp_filepath + ".hls-part.mp4"
                        # retVal = FFMPEG(None, url, access_token,
                        #                 temp_filepath).download()
                        ret_code = subprocess.Popen([
                            "yt-dlp", "--force-generic-extractor",
                            "--concurrent-fragments",
                            f"{concurrent_connections}", "--downloader",
                            "aria2c", "-o", f"{temp_filepath}", f"{url}"
                        ]).wait()
                        if retVal:
                            os.rename(temp_filepath, lecture_path)
                            print("      > HLS Download success")
                    else:
                        download_aria(url, lecture_dir, lecture_title + ".mp4")
                except Exception as e:
                    print(f"      > Error downloading lecture: ", e)
            else:
                print(
                    "      > Lecture '%s' is already downloaded, skipping..." %
                    lecture_title)
        else:
            print("      > Missing sources for lecture", lecture)


def parse_new(_udemy, quality, skip_lectures, dl_assets, dl_captions,
              caption_locale, keep_vtt, access_token, concurrent_connections):
    total_chapters = _udemy.get("total_chapters")
    total_lectures = _udemy.get("total_lectures")
    print(f"Chapter(s) ({total_chapters})")
    print(f"Lecture(s) ({total_lectures})")

    course_name = _udemy.get("course_title")
    course_dir = os.path.join(download_dir, course_name[:255])
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

            extension = lecture.get("extension")
            print(
                f"  > Processing lecture {lecture_index} of {total_lectures}")
            if not skip_lectures:
                if extension == "html":
                    html_content = lecture.get("html_content").encode(
                        "ascii", "ignore").decode("utf8")
                    lecture_path = os.path.join(
                        chapter_dir, "{}.html".format(sanitize(lecture_title)[:255]))
                    try:
                        with open(lecture_path, 'w') as f:
                            f.write(html_content)
                            f.close()
                    except Exception as e:
                        print("    > Failed to write html file: ", e)
                        continue
                else:
                    lecture_path = os.path.join(
                        chapter_dir,
                        sanitize(lecture_title) + ".mp4")
                    process_lecture(lecture, lecture_path, chapter_dir,
                                    quality, access_token,
                                    concurrent_connections)

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
                        process_caption(subtitle, lecture_title, chapter_dir,
                                        keep_vtt)


def course_info(course_data):
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


if __name__ == "__main__":
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
        "--concurrent-downloads",
        dest="concurrent_downloads",
        type=int,
        help="The number of maximum concurrent downloads for segments (HLS and DASH, must be a number 1-30)",
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

    dl_assets = False
    skip_lectures = False
    dl_captions = False
    caption_locale = "en"
    quality = None
    bearer_token = None
    portal_name = None
    course_name = None
    keep_vtt = False
    skip_hls = False
    concurrent_downloads = 10

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

    if args.load_from_file:
        print(
            "> 'load_from_file' was specified, data will be loaded from json files instead of fetched"
        )
    if args.save_to_file:
        print(
            "> 'save_to_file' was specified, data will be saved to json files")

    if not os.path.isfile(keyfile_path):
        print("> Keyfile not found! Did you rename the file correctly?")
        sys.exit(1)

    load_dotenv()
    access_token = None
    if args.bearer_token:
        access_token = args.bearer_token
    else:
        access_token = os.getenv("UDEMY_BEARER")

    udemy = Udemy(access_token)

    print("> Fetching course information, this may take a minute...")
    if not args.load_from_file:
        course_id, course_info = udemy._extract_course_info(args.course_url)
        print("> Course information retrieved!")
        if course_info and isinstance(course_info, dict):
            title = _clean(course_info.get("title"))
            course_title = course_info.get("published_title")
            portal_name = course_info.get("portal_name")

    print("> Fetching course content, this may take a minute...")
    if args.load_from_file:
        course_json = json.loads(
            open(os.path.join(os.getcwd(), "saved", "course_content.json"),
                 'r').read())
        title = course_json.get("title")
        course_title = course_json.get("published_title")
        portal_name = course_json.get("portal_name")
    else:
        course_json = udemy._extract_course_json(args.course_url, course_id,
                                                 portal_name)
    if args.save_to_file:
        with open(os.path.join(os.getcwd(), "saved", "course_content.json"),
                  'w') as f:
            f.write(json.dumps(course_json))
            f.close()

    print("> Course content retrieved!")
    course = course_json.get("results")
    resource = course_json.get("detail")

    if args.load_from_file:
        _udemy = json.loads(
            open(os.path.join(os.getcwd(), "saved", "_udemy.json")).read())
        if args.info:
            course_info(_udemy)
        else:
            parse_new(_udemy, quality, skip_lectures, dl_assets, dl_captions,
                      caption_locale, keep_vtt, access_token,
                      concurrent_downloads)
    else:
        _udemy = {}
        _udemy["access_token"] = access_token
        _udemy["course_id"] = course_id
        _udemy["title"] = title
        _udemy["course_title"] = course_title
        _udemy["chapters"] = []
        counter = -1

        if resource:
            print("> Trying to logout")
            udemy.session.terminate()
            print("> Logged out.")

        if course:
            print("> Processing course data, this may take a minute. ")
            lecture_counter = 0
            for entry in course:
                clazz = entry.get("_class")
                asset = entry.get("asset")
                supp_assets = entry.get("supplementary_assets")

                if clazz == "chapter":
                    lecture_counter = 0
                    lectures = []
                    chapter_index = entry.get("object_index")
                    chapter_title = "{0:02d} ".format(chapter_index) + _clean(
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
                        chapter_title = "{0:02d} ".format(
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
                        chapter_title = "{0:02d} ".format(
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

        if args.save_to_file:
            with open(os.path.join(os.getcwd(), "saved", "_udemy.json"),
                      'w') as f:
                f.write(json.dumps(_udemy))
                f.close()
            print("Saved parsed data to json")

        if args.info:
            course_info(_udemy)
        else:
            parse_new(_udemy, quality, skip_lectures, dl_assets, dl_captions,
                      caption_locale, keep_vtt, access_token,
                      concurrent_downloads)
