import random
import ssl
import time
from threading import Thread
from types import TracebackType
from typing import Any, Dict, Optional

import websocket
from websocket import WebSocketException

import messages
from jandy.api.zodaic import *
from jandy.resources.chemistry import run_chemistry_refresh

_LOGGING = logging.getLogger()
_FULL_STATE_REFRESH_SECONDS = 60


def _redact_sensitive_values(value):
	"""Return a logging-safe copy of a TCX message."""
	if isinstance(value, dict):
		redacted = {}
		for key, item in value.items():
			normalized_key = "".join(character for character in str(key).lower() if character.isalnum())
			if "token" in normalized_key or "password" in normalized_key or normalized_key == "authorization":
				redacted[key] = "[REDACTED]"
			else:
				redacted[key] = _redact_sensitive_values(item)
		return redacted
	if isinstance(value, list):
		return [_redact_sensitive_values(item) for item in value]
	return value


def _safe_field_paths(value, prefix="", depth=0):
	"""Return bounded structure paths without logging state values."""
	if depth >= 4:
		return ()
	paths = []
	if isinstance(value, dict):
		for key in sorted(value, key=str):
			key_text = str(key)
			if any(part in key_text.lower() for part in ("token", "password", "authorization")):
				continue
			path = f"{prefix}.{key_text}" if prefix else key_text
			paths.append(path)
			paths.extend(_safe_field_paths(value[key], path, depth + 1))
	elif isinstance(value, list) and value:
		paths.extend(_safe_field_paths(value[0], f"{prefix}[]", depth + 1))
	return tuple(paths)


def _expanded_state_payload(payload):
	"""Expose aggregate controller values to the existing state processors."""
	expanded = dict(payload)
	for component_name in ("main", "pib0"):
		component = payload.get(component_name)
		if not isinstance(component, dict):
			continue
		state = component.get("state")
		if isinstance(state, dict):
			reported = state.get("reported")
			if isinstance(reported, dict):
				expanded.update(reported)
		elif "metadata" not in component:
			# Component-specific delta messages are already unwrapped by
			# on_message(), for example {"pib0": {"water": 267}}.
			expanded.update(component)
	return expanded


class ZodaicClient(ZodaicWSBaseConnection):
	
	# async def __aenter__(self) -> "ZodaicClientWSAsyncConnection":
	#    return self
	
	def __aexit__(self,
				  exc_type: Optional[type],
				  exc_val: Optional[BaseException],
				  exc_tb: Optional[TracebackType],
				  ) -> None:
		self.on_close(self.ws, 1000, "Local CLient Exit")
	
	def open(self) -> None:
		
		url = self._format_websocket_url()
		
		_LOGGING.debug("Opening TCX WebSocket connection")
		connect_kwargs: Dict[str, Any] = {}
		if self._is_ssl_connection():
			ssl_context = ssl.SSLContext()
			ssl_context.verify_mode = ssl.CERT_NONE
			connect_kwargs["ssl"] = ssl_context
		headers = {
			"Authorization": self.get_acces_token(),
			"user-agent": "iAqualink/561 CFNetwork/1333.0.4 Darwin/21.5.0"
		}
		if CONST.websocketTrace:
			websocket.enableTrace(True)
		else:
			websocket.enableTrace(False)
		self._full_state_requested = False
		self._last_full_state_request_at = None
		try:
			self.ws = websocket.WebSocketApp(url, header=headers, on_open=self.start_listening,
											 on_message=self.on_message, on_close=self.on_close, on_pong=self.on_pong)
			i = random.randint(0, 9)
			self.wst = Thread(target=self.ws.run_forever, name=f"TCX_WS-{str(i)}",
							  kwargs={'ping_interval': CONST.PING_TIMER, 'ping_timeout': 10})
			self.wst.daemon = True
			self.wst.start()
			_LOGGING.debug("Thread Started")
		except WebSocketException as wsE:
			_LOGGING.error(f"(WebSocketException) Websocket Connections Exception while opening: {str(wsE)}")
		except Exception as e:
			_LOGGING.error(f"(Exception) Websocket Connections Exception while opening: {str(e)}")
			
	
	# websocket.send (messages.subscribe (self.user , self.device))
	
	def start_listening(self, ws) -> None:
		"""Open, and start listening."""
		self.ws.send(messages.subscribe(self.user, self.device))
	
	def on_open(self, ws=None):
		print("Opened connection")
		self.ws.send(messages.subscribe(self.user, self.device))
	
	def get_status(self):
		self.ws.send(messages.getState(self.device, self.clientToken))

	def _request_full_state_if_due(self, *, force=False):
		"""Refresh aggregate TCX values so temperatures cannot remain stale."""
		if not self.clientToken:
			return False
		now = time.monotonic()
		last_request = getattr(self, "_last_full_state_request_at", None)
		refresh_seconds = max(
			_FULL_STATE_REFRESH_SECONDS,
			getattr(CONST, "PING_TIMER", _FULL_STATE_REFRESH_SECONDS),
		)
		if not force and last_request is not None and now - last_request < refresh_seconds:
			return False
		self.get_status()
		self._last_full_state_request_at = now
		return True
	
	def _set_freeze(self):
		payload = {"freezeSP": 33}
		return messages.setState("tcx", payload, self.device)
	
	def send_state(self, desiredState):
		_LOGGING.debug("Sending Freeze Protection to TCX")
		_LOGGING.debug(f"Desired state sent to TCX: {str(desiredState)}")
		try:
			self.ws.send(desiredState)
		except WebSocketException as e:
			_LOGGING.error(f"Error sending requesst to TCX in send_state: {str(e)}")
	
	def on_message(self, ws, message) -> None:
		message = json.loads(message)
		if CONST.display_message:
			_LOGGING.debug(json.dumps(_redact_sensitive_values(message), indent=4, sort_keys=True))
		if "payload" in message:
			message_payload = message["payload"]
			if "state" in message_payload:
				if "reported" in message_payload["state"]:
					message_payload = message_payload["state"]["reported"]
				elif "desired" in message_payload["state"]:
					message_payload = message_payload["state"]["desired"]

			field_names = tuple(
				sorted(
					str(key)
					for key in message_payload
					if "token" not in str(key).lower()
				)
			)
			if field_names and field_names != getattr(self, "_last_logged_field_names", ()):
				_LOGGING.info("TCX state fields: %s", ", ".join(field_names))
				_LOGGING.info("TCX state paths: %s", ", ".join(_safe_field_paths(message_payload)))
				self._last_logged_field_names = field_names

			new_client_token = processClientToken(message)
			if new_client_token:
				self.clientToken = new_client_token

			# Request full device state once per socket connection. A valid
			# token retained from authentication is sufficient; ordinary state
			# messages are not required to repeat it.
			if not getattr(self, "_full_state_requested", False) and self.clientToken:
				_LOGGING.info("Requesting full device state to populate all sensors")
				self._full_state_requested = self._request_full_state_if_due(force=True)

			processor_payload = _expanded_state_payload(message_payload)
			processTCXTemp(processor_payload, self.ha_api)
			processFilterStatus(processor_payload, self.ha_api)
			processSWCStatus(processor_payload, self.ha_api)
			processLightStatus(processor_payload, self.ha_api)
			processHeaterStatus(processor_payload, self.ha_api)
			processECMStatus(processor_payload, self.ha_api)

			# Periodic chemistry refresh from HA (rate-limited to every 30 min)
			try:
				run_chemistry_refresh()
			except Exception:
				pass
	
	def on_pong(self, ws, ping_msg):
		_LOGGING.debug(f"Received Pong Server: {str(ping_msg)}")
		if self._request_full_state_if_due():
			_LOGGING.info("Requested periodic full device state refresh")
		desired = self._set_freeze()
		self.send_state(desired)
	
	def reconnect(self, force=False):
		if force:
			_LOGGING.info("Manuel reconnect called")
			if self.wst.is_alive():
				self.ws.close()
		
		retry_time = time.time() + CONST.reconnect_timer
		_LOGGING.info("Reconnecting at : %s" % time.ctime(retry_time))
		self.refersh_token()
		time.sleep(CONST.reconnect_timer)
		_LOGGING.info("Reconnecting Now")
		self.open()
	
	def on_close(self, ws, close_status_code, close_msg) -> None:
		_LOGGING.warning(f"TCX Connection closed.")
		_LOGGING.warning(f"TCX Close Code: {str(close_status_code)}  ")
		_LOGGING.warning(f"TCX Close MSG: {str(close_msg)}  ")
		if CONST.auto_reconnect and (str(close_status_code) == "1001"):
			_LOGGING.warning(f"TCX Auto Reconnect.")
			self.reconnect()
		elif CONST.auto_reconnect:
			_LOGGING.warning(f"Other close message then 1001 ")
			_LOGGING.warning(f"Two min pause before reconnect ")
			time.sleep(120)
			_LOGGING.warning(f"Reconnecting Now")
			self.reconnect()
		else:
			if self.ws:
				self.ws.close()
				if self.wst.is_alive():
					_LOGGING.info("Thread Still Alive")
				
