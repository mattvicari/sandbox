import json
import logging
import threading

from flask_restful import Resource

from jandy import CONST

_LOGGER = logging.getLogger()

class Status (Resource):
	@staticmethod
	def get ():
		#CONST.client.ws.on_open ()
		return json.dumps(CONST.system_info)

class Reconnect(Resource):
	@staticmethod
	def get():
		"""Trigger a reconnect in a background thread so the HTTP worker returns immediately.

		reconnect() sleeps for RECONNECT_TIMER seconds (default 60s) before reopening.
		Running that inside a gunicorn sync worker causes the worker to be killed by
		SIGABRT before the sleep completes, crashing the worker process.
		"""
		def _do_reconnect():
			if CONST.client and CONST.client.ws:
				if CONST.client.ws.ws:
					_LOGGER.info("Manual reconnect: closing existing websocket then reconnecting")
					CONST.client.ws.reconnect(True)
				else:
					_LOGGER.info("Manual reconnect: no open connection, opening fresh")
					CONST.client.ws.refersh_token()
					CONST.client.ws.open()
			else:
				_LOGGER.warning("Manual reconnect: no client available")

		t = threading.Thread(target=_do_reconnect, daemon=True, name="TCX_Reconnect")
		t.start()
		return {"Status": "Reconnecting"}