import json
import logging
import os
from typing import Any, Optional

import requests

from jandy.ha_api import HomeAssistantAPI

_LOGGING = logging.getLogger()


class ZodaicWSBaseConnection:
    _URL_FORMAT = "ws://{host}:{port}/devices"
    _SSL_URL_FORMAT = (
        "wss://{host}:{port}/devices"
    )
    _REST_URL_FORMAT = "{protocol}://{host}:{port}/api/v2/{route}"
    
    def __init__(
            self,
            host: str,
            *,
            endpoint: str = None,
            token: Optional[str] = None,
            token_file: Optional[str] = None,
            port: int = 443,
            timeout: Optional[float] = None,
            name: str = "ZodaicClient",
            user: dict,
            device: str,
            user_name: str,
            password: str
    ):
        self.host = host
        self.token = token
        self.token_file = token_file
        self.port = port
        self.timeout = None if timeout == 600 else timeout
        self.name = name
        self.endpoint = endpoint
        self.connection: Optional[Any] = None
        self._recv_loop: Optional[Any] = None
        self.user = user
        self.device = device
        self.clientToken = "540738|OmQtUBaUkqeGKQdiA8JTFg|NuGLKBG3P9X0ZGwhkC5GAs"
        self.ws = None
        self.ha_api = HomeAssistantAPI()
        self.wst = None
        self._username = user_name
        self._password = password
    
    def _is_ssl_connection(self) -> bool:
        return self.port == 443
    
    def _format_websocket_url(self) -> str:
        params = {
            "host": self.host,
            "port": self.port
        }
        
        if self._is_ssl_connection():
            return self._SSL_URL_FORMAT.format(**params)
        else:
            return self._URL_FORMAT.format(**params)
    
    def _format_rest_url(self, route: str = "") -> str:
        params = {
            "protocol": "https" if self._is_ssl_connection() else "http",
            "host": self.host,
            "port": self.port,
            "route": route,
        }
        
        return self._REST_URL_FORMAT.format(**params)
    
    def get_acces_token(self):
        return self.user["userPoolOAuth"]["IdToken"]
    
    def get_refresh_token(self):
        if "RefreshToken" in self.user["userPoolOAuth"]:
            return self.user["userPoolOAuth"]["RefreshToken"]
        else:
            return False

    def _auth(self) -> None:
        headers = {
            "content-type": "application/json",
            "user-agent": "iAqualink/561 CFNetwork/1333.0.4 Darwin/21.5.0", "accept": "*/*"
        }
        url = "https://prod.zodiac-io.com/users/v1/login"
        device_serial = None
        auth_obj = {
            "email": self._username,
            "password": self._password
        }
        x = requests.post(url, json=auth_obj, headers=headers)
        self.user = x.json()
        _LOGGING.debug(json.dumps(self.user, indent=4, sort_keys=True))
    def refersh_token(self):
        refersh = self.get_refresh_token()
        if refersh:
            _LOGGING.info("Refresh Token Found, using refresh token for re-authentication")
            headers = {"content-type": "application/json",
                       "user-agent": "iAqualink/561 CFNetwork/1333.0.4 Darwin/21.5.0",
                       "accept": "*/*"}
            url = "https://prod.zodiac-io.com/users/v1/refresh"
            auth_obj = {
                "email": self.user["email"],
                "refresh_token": refersh
            }
            x = requests.post(url, json=auth_obj, headers=headers)
            self.user = x.json()
            _LOGGING.info(f"Token Expires in: {int(self.user['userPoolOAuth']['ExpiresIn'])/60} minutes")
            return True
        else:
            _LOGGING.info("Refresh Token NOT Found, doing full authentication")
            self._auth()
            _LOGGING.info(f"Token Expires in: {int(self.user['userPoolOAuth']['ExpiresIn'])/60} minutes")
            return True
    
    def _websocket_event(self, event) -> None:
        """Handle websocket event."""
        print(event)
