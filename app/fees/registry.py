from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Category = Literal[
    "residential",
    "apartment",
    "dormitory",
    "commercial",
    "institutional",
    "special_use",
]


@dataclass(frozen=True)
class TemplateMeta:
    id: str
    label: str
    sheet_name: str
    category: Category
    description: str


TEMPLATE_REGISTRY: list[TemplateMeta] = [
    TemplateMeta(
        "residential_100k",
        "Residential — up to ₱100K",
        "Residential-100K",
        "residential",
        "Project cost ≤ ₱100,000",
    ),
    TemplateMeta(
        "residential_100k_plus",
        "Residential — ₱100K+",
        "Residential-100K+",
        "residential",
        "Project cost > ₱100,000 and ≤ ₱200,000",
    ),
    TemplateMeta(
        "residential_200k_plus",
        "Residential — ₱200K+",
        "Residential-200K+",
        "residential",
        "Project cost > ₱200,000",
    ),
    TemplateMeta(
        "apartment_500k",
        "Apartment / Townhouse — ₱500K",
        "ApartmentTownhouse-500K",
        "apartment",
        "Project cost ≤ ₱500,000",
    ),
    TemplateMeta(
        "apartment_500k_plus",
        "Apartment / Townhouse — ₱500K+",
        "ApartmentTownhouse-500K+",
        "apartment",
        "Project cost > ₱500,000 and ≤ ₱2,000,000",
    ),
    TemplateMeta(
        "apartment_2m_plus",
        "Apartment / Townhouse — ₱2M+",
        "ApartmentTownhouse-2M+",
        "apartment",
        "Project cost > ₱2,000,000",
    ),
    TemplateMeta(
        "dormitory_2m",
        "Dormitories — ₱2M",
        "Dormitories-2M",
        "dormitory",
        "Project cost ≤ ₱2,000,000",
    ),
    TemplateMeta(
        "dormitory_2m_plus",
        "Dormitories — ₱2M+",
        "Dormitories-2M+",
        "dormitory",
        "Project cost > ₱2,000,000",
    ),
    TemplateMeta(
        "commercial_100k",
        "Commercial / Industrial — ₱100K",
        "Comml,Indl,AgroInd-100K",
        "commercial",
        "Project cost ≤ ₱100,000",
    ),
    TemplateMeta(
        "commercial_100k_plus",
        "Commercial / Industrial — ₱100K+",
        "Comml,Indl,AgroInd-100K+",
        "commercial",
        "Project cost > ₱100,000 and ≤ ₱500,000",
    ),
    TemplateMeta(
        "commercial_500k_plus",
        "Commercial / Industrial — ₱500K+",
        "Comml,Indl,AgroInd-500K+",
        "commercial",
        "Project cost > ₱500,000 and ≤ ₱1,000,000",
    ),
    TemplateMeta(
        "commercial_1m_plus",
        "Commercial / Industrial — ₱1M+",
        "Comml,Indl,AgroInd-1M+",
        "commercial",
        "Project cost > ₱1,000,000 and ≤ ₱2,000,000",
    ),
    TemplateMeta(
        "commercial_2m_plus",
        "Commercial / Industrial — ₱2M+",
        "Comml,Indl,AgroIndl-2M+",
        "commercial",
        "Project cost > ₱2,000,000",
    ),
    TemplateMeta(
        "institutional_2m",
        "Institutional — ₱2M",
        "Institutional-2M",
        "institutional",
        "Project cost ≤ ₱2,000,000",
    ),
    TemplateMeta(
        "institutional_2m_plus",
        "Institutional — ₱2M+",
        "Institutional-2M+",
        "institutional",
        "Project cost > ₱2,000,000",
    ),
    TemplateMeta(
        "special_use_2m",
        "Special use — ₱2M",
        "SpecialUse-2M",
        "special_use",
        "Project cost ≤ ₱2,000,000",
    ),
    TemplateMeta(
        "special_use_2m_plus",
        "Special use — ₱2M+",
        "SpecialUse-2M+",
        "special_use",
        "Project cost > ₱2,000,000",
    ),
]

_BY_ID = {t.id: t for t in TEMPLATE_REGISTRY}


def get_template(template_id: str) -> TemplateMeta:
    if template_id not in _BY_ID:
        raise KeyError(template_id)
    return _BY_ID[template_id]


def list_categories() -> list[tuple[str, str]]:
    return [
        ("residential", "Residential"),
        ("apartment", "Apartment / Townhouse"),
        ("dormitory", "Dormitories"),
        ("commercial", "Commercial / Industrial / Agro-industrial"),
        ("institutional", "Institutional"),
        ("special_use", "Special use"),
    ]


def suggest_template(category: str, project_cost: float) -> str:
    c = float(project_cost)
    if category == "residential":
        if c <= 100_000:
            return "residential_100k"
        if c <= 200_000:
            return "residential_100k_plus"
        return "residential_200k_plus"
    if category == "apartment":
        if c <= 500_000:
            return "apartment_500k"
        if c <= 2_000_000:
            return "apartment_500k_plus"
        return "apartment_2m_plus"
    if category == "dormitory":
        if c <= 2_000_000:
            return "dormitory_2m"
        return "dormitory_2m_plus"
    if category == "commercial":
        if c <= 100_000:
            return "commercial_100k"
        if c <= 500_000:
            return "commercial_100k_plus"
        if c <= 1_000_000:
            return "commercial_500k_plus"
        if c <= 2_000_000:
            return "commercial_1m_plus"
        return "commercial_2m_plus"
    if category == "institutional":
        if c <= 2_000_000:
            return "institutional_2m"
        return "institutional_2m_plus"
    if category == "special_use":
        if c <= 2_000_000:
            return "special_use_2m"
        return "special_use_2m_plus"
    raise ValueError(f"Unknown category: {category}")
