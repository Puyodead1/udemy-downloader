from udemy_downloader.Session import Session


class UdemyAuth(object):
    def __init__(self):
        self._session = Session()

    def update_token(self, bearer_token=None):
        if bearer_token:
            self._session._set_auth_headers(bearer_token=bearer_token)
            return self._session
        else:
            return None
