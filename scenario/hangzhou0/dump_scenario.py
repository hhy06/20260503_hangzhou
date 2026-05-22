"""Print all configuration data for this scenario."""

import sys
from pathlib import Path

# Allow running as `python scenario/hangzhou0/dump_scenario.py`
# or `python -m scenario.hangzhou0.dump_scenario` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scenario.hangzhou0 import config

config.dump_config()
