import ssl
from typing import Optional

from requests.adapters import HTTPAdapter


class SSLCiphers(HTTPAdapter):
    """
    Custom HTTP Adapter to change the TLS Cipher set, and therefore it's fingerprint.
    """

    def __init__(self, cipher_list: Optional[str] = None, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False  # For some reason this is needed to avoid a verification error
        self._ssl_context = ctx
        # You can set ciphers but Python's default cipher list should suffice.
        # This cipher list differs to the default Python-requests one.
        if cipher_list:
            self._ssl_context.set_ciphers(cipher_list)
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._ssl_context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = self._ssl_context
        return super().proxy_manager_for(*args, **kwargs)
