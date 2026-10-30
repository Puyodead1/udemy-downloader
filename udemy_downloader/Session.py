import logging
import time
from http.cookiejar import CookieJar

import requests

from udemy_downloader.constants import LOGGER_NAME
from udemy_downloader.tls import SSLCiphers

logger = logging.getLogger(LOGGER_NAME)


class Session(object):
    def __init__(self, headers=None):
        self._session = requests.sessions.Session()
        self._session.headers.update(headers or {})
        # alias the live session headers so updates are sent with requests
        self._headers = self._session.headers
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
            if r.status_code not in [502, 503]:
                if not r.ok:
                    logger.error(f"Failed request {url}: {r.status_code} {r.reason}")
                return r
            logger.warning(f"{r.status_code} {r.reason}, retrying (attempt {i + 1}/10)...")
            time.sleep(0.8)
        return r

    def _post(self, url, data, redirect=True):
        r = self._session.post(url, data, allow_redirects=redirect)
        if not r.ok:
            logger.debug(f"Response body: {r.text}")
            raise Exception(f"{r.status_code} {r.reason}")
        return r

    def set_cookiejar(self, cookiejar: CookieJar):
        self._session.cookies = cookiejar

    def terminate(self):
        self._session.close()
