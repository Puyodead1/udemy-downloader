from udemy_downloader.constants import HEADERS
from udemy_downloader.Session import Session


class UdemyAuth(object):
    def __init__(self):
        self._session = Session(HEADERS)

    def update_token(self, bearer_token=None):
        if bearer_token:
            self._session._set_auth_headers(bearer_token=bearer_token)
            return self._session
        else:
            return None
