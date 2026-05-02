from __future__ import annotations

from datetime import datetime


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]
