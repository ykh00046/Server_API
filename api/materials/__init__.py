"""Material-requests intake subsystem (materials-api-v1).

Receives 자재요청 backup data from the webcloring-pdf 포털 자동화 (replacing the
prior Google Sheets backup). Public surface is the `store` facade + schemas.
"""
from __future__ import annotations

from . import automation, runs, store
from .schemas import (
    BackupResult,
    MaterialBackupRequest,
    MaterialPublic,
    MaterialRow,
    MaterialRun,
    RunTriggerResult,
)

__all__ = [
    "BackupResult",
    "MaterialBackupRequest",
    "MaterialPublic",
    "MaterialRow",
    "MaterialRun",
    "RunTriggerResult",
    "automation",
    "runs",
    "store",
]
