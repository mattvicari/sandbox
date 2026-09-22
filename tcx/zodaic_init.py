import sys

from jandy import CONST as _JANDY_CONST

# Processors do `import CONST` while Flask uses `from jandy import CONST`.
# Those are the same file loaded as two module objects unless we alias them.
sys.modules["CONST"] = _JANDY_CONST

from .connection import ZodaicWSBaseConnection
from .messageProcessor import *
