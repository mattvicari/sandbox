import json

from .pump_switch import pump_switch
from .setMessage import state as setState


def subscribe(userId,target):
	return json.dumps({
			"action"   : "subscribe",
			"version"  : 1,
			"namespace": "authorization",
			"payload"  : {
					"userId": userId["id"]
			},
			"service"  : "Authorization",
			"target"   : target
		})

def old_setState(target):
	return json.dumps({
			"action"   : "setState",
			"version"  : 1,
			"namespace": "tcx",
			"payload"  : {
					"state"      : {
							"desired": {
									"freezeSP": 33
							}
					}
			},
			"service"  : "StateController",
			"target"   : target
	})
def getState(target,clientToken):
	return json.dumps({
	  "action": "getState",
	  "version": 1,
	  "namespace": "TCX",
	  "service": "StateController",
	  "target": target,
	  "payload" : {
		  "clientToken": clientToken
	  }
	})

def getStateNoPayload(target):
	return json.dumps({
	  "action": "getState",
	  "version": 1,
	  "namespace": "TCX",
	  "service": "StateController",
	  "target": target
	})

def getFilterStatus(target):
	return json.dumps({
	  "action": "getState",
	  "version": 1,
	  "namespace": "filtration",
	  "service": "StateController",
	  "target": target
	})
