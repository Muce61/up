from __future__ import annotations

from datetime import date
from pathlib import Path
import json
import hashlib
import sys

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.akshare_adapter import PRICE_COLUMNS
from src.data.snapshot import build_price_snapshot
