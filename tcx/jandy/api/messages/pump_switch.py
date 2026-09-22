from .setMessage import state
def pump_switch(target,value):
	desired = {"pool": { "st": value}}
	return state("filtration",desired,target)


