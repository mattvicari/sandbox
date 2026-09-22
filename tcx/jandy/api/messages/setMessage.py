import json


def state(namespace, state, target):
	return json.dumps ({
		"action": "setState",
		"version": 1,
		"namespace": namespace,
		"payload": {
			"state": {
				"desired": state
				
			}
		},
		"service": "StateController",
		"target": target
	})
