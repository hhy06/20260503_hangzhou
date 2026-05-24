"""Print all configuration data for this scenario.

Usage (from project root)::

    python -m scenario.t_hangzhou1.dump_scenario

Note:
    This module uses **relative imports** so the scenario folder can be
    freely copied and renamed.  It must NOT be executed directly as a
    script (``python path/to/dump_scenario.py``) — always use ``-m``.
"""

from . import config

config.dump_config()
