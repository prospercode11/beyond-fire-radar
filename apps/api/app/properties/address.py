from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Optional

ADDRESS_NORMALIZATION_VERSION = "address-normalization.v1"

_DIRECTIONALS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}
_STREET_TYPES = {
    "ALY": "ALLEY",
    "ALLEY": "ALLEY",
    "AVE": "AVENUE",
    "AVENUE": "AVENUE",
    "BLVD": "BOULEVARD",
    "BOULEVARD": "BOULEVARD",
    "CIR": "CIRCLE",
    "CIRCLE": "CIRCLE",
    "CT": "COURT",
    "COURT": "COURT",
    "DR": "DRIVE",
    "DRIVE": "DRIVE",
    "HWY": "HIGHWAY",
    "HIGHWAY": "HIGHWAY",
    "LN": "LANE",
    "LANE": "LANE",
    "PKWY": "PARKWAY",
    "PARKWAY": "PARKWAY",
    "PL": "PLACE",
    "PLACE": "PLACE",
    "RD": "ROAD",
    "ROAD": "ROAD",
    "SQ": "SQUARE",
    "SQUARE": "SQUARE",
    "ST": "STREET",
    "STREET": "STREET",
    "TER": "TERRACE",
    "TERRACE": "TERRACE",
    "TRL": "TRAIL",
    "TRAIL": "TRAIL",
    "WAY": "WAY",
}


@dataclass(frozen=True)
class NormalizedAddress:
    original: str
    normalized: str
    precision: str
    house_number: Optional[str]
    street_prefix: Optional[str]
    street_name: Optional[str]
    street_type: Optional[str]
    street_suffix: Optional[str]
    unit: Optional[str]
    municipality: Optional[str]
    postal_code: Optional[str]
    street_tokens: tuple[str, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _clean(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\xa0", " ").upper()
    text = re.sub(r"[.,]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _postal(value: object) -> Optional[str]:
    cleaned = _clean(value)
    if not cleaned:
        return None
    # A five-digit street number is common in Sarasota records. Postal codes are
    # treated as the final token when parsing a complete address so a leading
    # house number such as 11704 is never mistaken for a ZIP code.
    match = re.search(r"\b(\d{5}(?:-\d{4})?)\b\s*$", cleaned)
    return match.group(1) if match else None


def _unit_from_text(text: str) -> tuple[str, Optional[str]]:
    unit_match = re.search(
        r"(?:#|\b(?:APT|APARTMENT|UNIT|STE|SUITE|BLDG|BUILDING|LOT)\b)\s*([A-Z0-9-]+)",
        text,
    )
    if not unit_match:
        return text, None
    unit = unit_match.group(1)
    return (text[: unit_match.start()] + text[unit_match.end() :]).strip(), unit


def _street_parts(text: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    tokens = text.split()
    if not tokens:
        return None, None, None, None
    prefix = tokens[0] if tokens[0] in _DIRECTIONALS else None
    if prefix:
        tokens = tokens[1:]
    suffix = tokens[-1] if tokens and tokens[-1] in _DIRECTIONALS else None
    if suffix:
        tokens = tokens[:-1]
    street_type = None
    if tokens and tokens[-1] in _STREET_TYPES:
        street_type = _STREET_TYPES[tokens.pop()]
    street_name = " ".join(tokens) or None
    return prefix, street_name, street_type, suffix


def _street_tokens(*parts: Optional[str]) -> tuple[str, ...]:
    return tuple(part for part in (parts) if part)


def normalize_address(
    address: object,
    *,
    municipality: object = None,
    postal_code: object = None,
    unit: object = None,
) -> NormalizedAddress:
    original = "" if address is None else str(address).strip()
    text = _clean(original)
    city = _clean(municipality) or None
    zip_code = _postal(postal_code) or _postal(text)
    warnings: list[str] = []
    if city is None and "," in original:
        comma_parts = [_clean(part) for part in original.split(",") if _clean(part)]
        if len(comma_parts) >= 2:
            tail = comma_parts[-1]
            tail_without_zip = re.sub(r"\b\d{5}(?:-\d{4})?\b", " ", tail).strip()
            tail_without_state = re.sub(r"\b(?:FL|FLORIDA)\b", " ", tail_without_zip).strip()
            if tail_without_state:
                city = tail_without_state
            elif len(comma_parts) >= 3:
                city = comma_parts[-2]
    text = re.sub(r"\b(?:FL|FLORIDA)\b", " ", text).strip()
    if zip_code:
        text = re.sub(rf"\b{re.escape(zip_code)}\b", " ", text).strip()
    if city:
        text = re.sub(rf"\b{re.escape(city)}\b", " ", text).strip()
    text, parsed_unit = _unit_from_text(text)
    selected_unit = _clean(unit) or parsed_unit
    if selected_unit:
        selected_unit = selected_unit.lstrip("#")

    if not text:
        return NormalizedAddress(
            original=original,
            normalized="",
            precision="unusable",
            house_number=None,
            street_prefix=None,
            street_name=None,
            street_type=None,
            street_suffix=None,
            unit=selected_unit,
            municipality=city,
            postal_code=zip_code,
            street_tokens=(),
            warnings=("empty_address",),
        )

    if re.search(r"\s(?:&|AND|AT)\s", text) or "INTERSECTION" in text:
        tokens = tuple(token for token in re.split(r"\s+(?:&|AND|AT)\s+", text) if token)
        return NormalizedAddress(
            original=original,
            normalized=" & ".join(tokens + tuple(filter(None, (city, zip_code)))),
            precision="intersection",
            house_number=None,
            street_prefix=None,
            street_name=" ".join(tokens) or None,
            street_type=None,
            street_suffix=None,
            unit=selected_unit,
            municipality=city,
            postal_code=zip_code,
            street_tokens=tokens,
            warnings=("intersection_location",),
        )

    block_match = re.match(r"^(?:BLOCK\s+OF\s+)?(\d+)\s*[-–]\s*(\d+)\s+(.+)$", text)
    if block_match or text.startswith("BLOCK OF "):
        block_text = block_match.group(3) if block_match else text.removeprefix("BLOCK OF ").strip()
        prefix, street_name, street_type, suffix = _street_parts(block_text)
        normalized = " ".join(
            part for part in (street_name, street_type, suffix, city, zip_code) if part
        )
        return NormalizedAddress(
            original=original,
            normalized=normalized,
            precision="street_block",
            house_number=(block_match.group(1) + "-" + block_match.group(2))
            if block_match
            else None,
            street_prefix=prefix,
            street_name=street_name,
            street_type=street_type,
            street_suffix=suffix,
            unit=selected_unit,
            municipality=city,
            postal_code=zip_code,
            street_tokens=_street_tokens(prefix, street_name, street_type, suffix),
            warnings=("street_block_location",),
        )

    house_match = re.match(r"^(\d+[A-Z]?)(?:\s+|$)(.*)$", text)
    house_number = house_match.group(1) if house_match else None
    street_text = house_match.group(2) if house_match else text
    if city:
        street_text = re.sub(rf"\b{re.escape(city)}\b", " ", street_text).strip()
    street_tokens_before_type = street_text.split()
    route_like = (
        re.match(
            r"^(?:\d+\s+)?(?:I[- ]\d+|US[- ]?\d+|SR[- ]?\d+|STATE ROAD|COUNTY ROAD)",
            text,
        )
        is not None
    )
    if not route_like:
        for index, token in enumerate(street_tokens_before_type):
            if token in _STREET_TYPES:
                street_text = " ".join(street_tokens_before_type[: index + 1])
                break
    if route_like:
        precision = "highway"
        warnings.append("highway_or_route_location")
    elif house_number:
        precision = "exact_address_with_unit" if selected_unit else "exact_address"
    else:
        precision = "landmark"
        warnings.append("missing_house_number")
    prefix, street_name, street_type, suffix = _street_parts(street_text)
    normalized = " ".join(
        part
        for part in (
            house_number,
            prefix,
            street_name,
            street_type,
            suffix,
            selected_unit,
            city,
            zip_code,
        )
        if part
    )
    return NormalizedAddress(
        original=original,
        normalized=normalized,
        precision=precision,
        house_number=house_number,
        street_prefix=prefix,
        street_name=street_name,
        street_type=street_type,
        street_suffix=suffix,
        unit=selected_unit,
        municipality=city,
        postal_code=zip_code,
        street_tokens=_street_tokens(prefix, street_name, street_type, suffix),
        warnings=tuple(warnings),
    )
