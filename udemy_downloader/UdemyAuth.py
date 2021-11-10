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

from Session import Session
import sys


class UdemyAuth(object):
    def __init__(self, username="", password="", cache_session=False):
        self.username = username
        self.password = password
        self._cache = cache_session
        self._session = Session()

    def authenticate(self, access_token, cookies):
        if access_token:
            self._session._set_auth_headers(
                access_token=access_token, cookies=cookies)
            self._session._session.cookies.update(
                {"access_token": access_token})
            return self._session, access_token
        else:
            raise RuntimeError("No access token is present")
