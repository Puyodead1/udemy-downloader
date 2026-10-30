import logging
import time
from http.cookiejar import CookieJar

from curl_cffi import requests

from udemy_downloader.constants import HEADERS, LOGGER_NAME, VISIT_URL

logger = logging.getLogger(LOGGER_NAME)


class Session(object):
    def __init__(self, headers=None):
        # impersonate a real browser's TLS fingerprint to get past Cloudflare
        self._session = requests.Session(impersonate="chrome120")
        headers = dict(HEADERS if headers is None else headers)
        # the impersonated browser supplies its own User-Agent
        headers.pop("User-Agent", None)
        self._session.headers.update(headers)
        # alias the live session headers so updates are sent with requests
        self._headers = self._session.headers

    def visit(self, portal_name: str) -> bool:
        """Make a visit request to pick up the Cloudflare cookies before using the API"""
        url = VISIT_URL.format(portal_name=portal_name)
        logger.info(f"Visiting {url} to clear Cloudflare...")
        try:
            r = self._session.get(url, timeout=120)
        except requests.exceptions.RequestException as e:
            logger.error(f"Request Exception: {e}")
            return False

        if "challenge-platform" in r.text or "<title>Just a moment...</title>" in r.text:
            logger.error("Cloudflare Challenge triggered. Fingerprint failed.")
            return False
        if not r.ok:
            logger.error(f"Visit request failed: {r.status_code}")
            return False
        logger.debug("Visit request successful")
        return True

    def _set_auth_headers(self, bearer_token=""):
        self._headers["Authorization"] = "Bearer {}".format(bearer_token)
        self._headers["X-Udemy-Authorization"] = "Bearer {}".format(bearer_token)

    def _get(self, url, params=None):
        for i in range(10):
            # a long timeout avoids "Operation timed out after 30002 milliseconds" on slow responses
            r = self._session.get(url, params=params, timeout=120)
            if r.status_code not in [502, 503]:
                if not r.ok:
                    logger.error(f"Failed request {url}: {r.status_code} {r.reason}")
                return r
            logger.warning(f"{r.status_code} {r.reason}, retrying (attempt {i + 1}/10)...")
            time.sleep(0.8)
        return r

    def _post(self, url, data, redirect=True):
        r = self._session.post(url, data=data, allow_redirects=redirect, timeout=120)
        if not r.ok:
            logger.debug(f"Response body: {r.text}")
            raise Exception(f"{r.status_code} {r.reason}")
        return r

    def set_cookiejar(self, cookiejar: CookieJar):
        self._session.cookies.update(cookiejar)

    def terminate(self):
        self._session.close()
