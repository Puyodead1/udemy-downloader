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
        self._session.headers.update(self._headers)
        # self.cookiejar = CookieJar()
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
            r = self._session.get(url, params=params)
            if not r.ok and r.status_code not in [502, 503]:
                print(r.text)
                logger.error("Failed request " + url)
                logger.error(f"{r.status_code} {r.reason}, retrying (attempt {i} )...")
                time.sleep(0.8)

            return r

    def _post(self, url, data, redirect=True):
        r = self._session.post(url, data, allow_redirects=redirect)
        if not r.ok:
            print(r.text)
            raise Exception(f"{r.status_code} {r.reason}")
        return r

    def set_cookiejar(self, cookiejar: CookieJar):
        self._session.cookies = cookiejar
