import json
import logging
import os

import requests

import jandy.client
from jandy import CONST

logger = logging.getLogger('websockets')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

_LOGGER = logging.getLogger(__name__)


class ConnectionException(Exception):
	"""Any failure to connect to Zodaic System"""


class JandyTCX:
	def __init__(self, user_name, password):
		self.user_name = user_name
		self.password = password
		self.zodaic_io_url = "https://prod.zodiac-io.com/devices/v2/"
		self.user = None
		self._api_key = "EOOEMOW4YR6QNB07"
		self.devices = None
		self.ws = None
	
	def device_connection(self, device_serial) -> None:
		headers = {
			"content-type": "application/json",
			"user-agent": "iAqualink/561 CFNetwork/1333.0.4 Darwin/21.5.0",
			"accept": "*/*",
			"authorization": self.user["userPoolOAuth"]["IdToken"]
		}
		
		x = requests.get(f"https://prod.zodiac-io.com/devices/v2/{device_serial}/ota",
						 headers=headers)
		_LOGGER.debug(json.dumps(x.json(), indent=4, sort_keys=True))
		
		self.ws = jandy.client.ZodaicClient(host="prod-socket.zodiac-io.com",
											user=self.user,
											device=device_serial,user_name=self.user_name,password=self.password)
	
	def jandy_auth(self) -> None:
		headers = {
			"content-type": "application/json",
			"user-agent": "iAqualink/561 CFNetwork/1333.0.4 Darwin/21.5.0", "accept": "*/*"
		}
		url = "https://prod.zodiac-io.com/users/v1/login"
		device_serial = None
		auth_obj = {
			"email": self.user_name,
			"password": self.password
		}
		x = requests.post(url, json=auth_obj, headers=headers)
		body = x.json()
		if not isinstance(body, dict) or "userPoolOAuth" not in body:
			_LOGGER.error(
				"Jandy login failed (HTTP %s): %s", x.status_code, x.text[:500]
			)
			raise ConnectionException(
				f"Jandy login did not return credentials (HTTP {x.status_code}): "
				f"{x.text[:500]!r}"
			)
		self.user = body
		_LOGGER.info(f"Token Expires in: {int(self.user['userPoolOAuth']['ExpiresIn'])/60} minutes")
		if CONST.display_message:
			_LOGGER.debug(json.dumps(self.user, indent=4, sort_keys=True))
	
	def get_devices(self) -> dict:
		devices_url = "https://r-api.iaqualink.net/devices.json"
		
		x = requests.get(devices_url, params={
			"user_id": self.user["id"], "api_key": self._api_key,
			"authentication_token": self.user["authentication_token"]
		})
		self.devices = x.json()
		if CONST.display_message:
			_LOGGER.debug(json.dumps(self.devices, indent=4, sort_keys=True))
		return self.devices


def start():
	jandy_username = os.getenv("JANDY_USERNAME")
	jandy_password = os.getenv("JANDY_PASSWORD")
	client = JandyTCX(jandy_username, jandy_password)
	client.jandy_auth()
	devices = client.get_devices()
	for device in devices:
		if device["device_type"] == "tcx":
			device_serial = device["serial_number"]
			if device_serial:
				client.device_connection(device_serial)
				client.ws.open()
				client.ws.start_listening()


if __name__ == "__main__":
	start()
