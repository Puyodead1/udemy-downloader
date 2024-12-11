import logging
import time
from http.cookiejar import CookieJar

import requests

from udemy_downloader.constants import LOGGER_NAME
from udemy_downloader.tls import SSLCiphers

logger = logging.getLogger(LOGGER_NAME)


class Session(object):
    def __init__(self, headers={}):
        self._headers = headers
        self._session = requests.sessions.Session()
        # this is to bypass TLS fingerprinting
        self._session.mount(
            "https://",
            SSLCiphers(
                cipher_list="ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-SHA256:AES256-SH"
            ),
        )

    def _set_auth_headers(self, bearer_token=""):
        self._headers["Authorization"] = "Bearer {}".format(bearer_token)
        self._headers["X-Udemy-Authorization"] = "Bearer {}".format(bearer_token)

    def _get(self, url, params=None):
        for i in range(10):
            session = self._session.get(url, headers=self._headers, cookies=self.cookiejar, params=params)
            if session.ok or session.status_code in [502, 503]:
                return session
            if not session.ok:
                logger.error("Failed request " + url)
                logger.error(f"{session.status_code} {session.reason}, retrying (attempt {i} )...")
                time.sleep(0.8)

    def _post(self, url, data, redirect=True):
        session = self._session.post(url, data, headers=self._headers, allow_redirects=redirect, cookies=self.cookiejar)
        if session.ok:
            return session
        if not session.ok:
            raise Exception(f"{session.status_code} {session.reason}")

    def set_cookiejar(self, cookiejar: CookieJar):
        self.cookiejar = cookiejar
