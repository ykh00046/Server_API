"""Dataset registry for keyword-partitioned intake (materials-datasets-v1).

The webcloring-pdf 포털 자동화 collects documents by 검색 키워드. Different
keywords serve different business purposes (자재요청 vs 액상바인더출고 …) and
must NOT share a table — so each maps to its own *dataset*: an isolated table
pair (data + run history) exposed under its own route prefix.

자재 keeps the original `material_requests` table and `/materials` routes for
full backward compatibility. New purposes are added by appending one Dataset
entry here — the store schema, router factory, and bot routing all read this
registry, so there is nothing else to touch.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dataset:
    """One keyword-partitioned dataset.

    Attributes:
        key:        stable identifier (used in logs / lookups).
        table:      SQLite table for the rows.
        runs_table: SQLite table for backup/automation run history.
        prefix:     HTTP route prefix (e.g. "/materials", "/binder").
        title:      OpenAPI tag / human label.
        keywords:   포털 검색어들이 이 데이터셋으로 매핑된다(봇 라우팅 참조용).
    """

    key: str
    table: str
    runs_table: str
    prefix: str
    title: str
    keywords: tuple[str, ...]


# 등록된 데이터셋. 새 용도 추가 = 여기에 한 줄.
DATASETS: dict[str, Dataset] = {
    "materials": Dataset(
        key="materials",
        table="material_requests",
        runs_table="material_runs",
        prefix="/materials",
        title="Materials",
        keywords=("자재", "접수"),
    ),
    "binder": Dataset(
        key="binder",
        table="binder_requests",
        runs_table="binder_runs",
        prefix="/binder",
        title="Binder",
        keywords=("PBHAv1.0",),
    ),
}

# 키워드 매핑이 없을 때의 기본 데이터셋 (하위 호환: 기존 자재).
DEFAULT_DATASET = DATASETS["materials"]


def all_datasets() -> list[Dataset]:
    return list(DATASETS.values())


def get_dataset(key: str) -> Dataset:
    return DATASETS[key]


def dataset_for_keyword(keyword: str | None) -> Dataset:
    """검색 키워드를 데이터셋으로 매핑한다. 매칭이 없으면 기본(materials)."""
    if keyword:
        for ds in DATASETS.values():
            if keyword in ds.keywords:
                return ds
    return DEFAULT_DATASET
