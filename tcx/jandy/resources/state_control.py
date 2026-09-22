import logging

from flask_restful import Resource, reqparse

from jandy import CONST
from jandy.api import messages

_LOGGING = logging.getLogger()
parser = reqparse.RequestParser()
parser.add_argument('namespace')
parser.add_argument("desired",type=dict)


def read_request(nameSpace,request):
	desired = messages.setState(nameSpace, request, CONST.DEVICE_SERIAL)
	if CONST.client.ws:
		CONST.client.ws.send_state(desired)
		_LOGGING.debug(f"State message sent to TCX: {str(desired)}")
	else:
		_LOGGING.error("No Connect websocket client")
	
class TCXStateControl(Resource):
	@staticmethod
	def post():
		args = parser.parse_args()
		_LOGGING.info(f"Request to set pool to {str(args)}")
		read_request(args["namespace"],args["desired"])
		return f"Sent Desired state to pool {str(args)}"
