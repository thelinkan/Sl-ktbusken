"""What the GEDCOM import can do, as flags other parts of the application read.

``NON_DESTRUCTIVE_UPDATE_AVAILABLE`` is ``False`` until an update import stops
overwriting names, notes, title and occupation of existing persons. The merge
wizard shows a warning while it is ``False`` (Requirements 26.15, 30.13).
"""

NON_DESTRUCTIVE_UPDATE_AVAILABLE = False
