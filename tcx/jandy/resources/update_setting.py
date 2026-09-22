from jandy.api import messages
from flask_restful import Resource
from jandy import CONST


class PoolSwitch (Resource):
	def get (self):
		CONST.client.ws.send(messages.turn_on_pump (CONST.DEVICE_SERIAL))
		return "Pool_Turned_ON"
