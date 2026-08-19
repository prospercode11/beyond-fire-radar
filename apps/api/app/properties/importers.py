from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Optional
from xml.etree import ElementTree

from app.properties.address import NormalizedAddress, normalize_address

PROPERTY_PARSER_VERSION = "sarasota.property.v1"
PROPERTY_SCHEMA_VERSION = "sarasota.property.schema.v1"
PROPERTY_TRANSFORMATION_VERSION = "property-normalization.v1"
PROPERTY_REQUIRED_FIELDS = ("parcel_id", "address")

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "parcel_id": (
        "parcel_id",
        "parcel",
        "parcel_number",
        "folio",
        "folio_id",
        "folio_number",
        "pid",
        "strap",
    ),
    "address": (
        "address",
        "situs_address",
        "site_address",
        "site_addr",
        "site_address_no_unit",
        "property_address",
        "situs",
        "phy_addr1",
        "physical_address",
    ),
    "municipality": (
        "municipality",
        "city",
        "site_city",
        "city_name",
        "town",
        "jurisdiction",
        "phy_city",
    ),
    "postal_code": ("postal_code", "zip", "zipcode", "zip_code", "site_zip", "phy_zipcd"),
    "county": ("county", "county_name"),
    "property_use_code": ("property_use_code", "use_code", "land_use_code", "dor_uc"),
    "property_use_category": ("property_use_category", "property_type", "use_category", "land_use"),
    "owner_name": (
        "owner_name",
        "owner",
        "owner1",
        "owner_1",
        "owner_of_record",
        "taxpayer_name",
        "own_name",
    ),
    "mailing_address": (
        "mailing_address",
        "owner_mailing_address",
        "tax_mailing_address",
        "mail_addr",
        "own_addr1",
        "own_addr2",
    ),
    "year_built": ("year_built", "built_year", "yearbuilt", "act_yr_blt"),
    "effective_year_built": ("effective_year_built", "effective_built_year", "eff_yr_blt"),
    "building_area": (
        "building_area",
        "building_sqft",
        "gross_building_area",
        "actual_area",
        "bldg_actual_area",
        "bldg_area",
        "total_area",
        "tot_lvg_area",
    ),
    "living_area": ("living_area", "living_sqft", "heated_area"),
    "number_of_buildings": ("number_of_buildings", "building_count", "structures", "no_buldng"),
    "number_of_units": ("number_of_units", "units", "unit_count", "no_res_unts"),
    "stories": ("stories", "story_count", "floors"),
    "latitude": ("latitude", "lat", "y", "y_coordinate"),
    "longitude": ("longitude", "lon", "lng", "long", "x", "x_coordinate"),
    "grid": ("grid", "dispatch_grid", "zone"),
    "master_parcel_id": ("master_parcel_id", "master_parcel", "parent_parcel"),
    "unit": ("unit", "unit_number", "apartment", "apt", "condo_unit"),
    "address_alias": ("address_alias", "alternate_address", "alias_address", "complex_name"),
    "geometry": ("geometry", "geometry_json", "wkt", "geojson"),
    "sales_count": ("sales_count",),
    "last_sale_date": ("last_sale_date",),
    "last_sale_price": ("last_sale_price",),
    "last_sale_legal_reference": ("last_sale_legal_reference",),
    "last_sale_deed_type": ("last_sale_deed_type",),
    "last_sale_recording_date": ("last_sale_recording_date",),
    "total_value": ("total_value", "jv"),
    "land_value": ("land_value", "lnd_val"),
    "building_value": ("building_value", "nconst_val"),
    "assessed_value": ("assessed_value", "av_sd"),
    "taxable_value": ("taxable_value", "tv_sd"),
    "bedrooms": ("bedrooms",),
    "rooms": ("rooms",),
    "outbuilding_count": ("outbuilding_count",),
    "source_parcel_sales_sha256": ("source_parcel_sales_sha256",),
    "source_detailed_sha256": ("source_detailed_sha256",),
    "source_geometry_service": ("source_geometry_service",),
    "source_geometry_layer": ("source_geometry_layer",),
    "source_rows": ("source_rows",),
}


@dataclass(frozen=True)
class PropertyParseIssue:
    code: str
    message: str
    row_number: Optional[int] = None
    raw_payload: Optional[str] = None
    severity: str = "error"


@dataclass(frozen=True)
class NormalizedPropertyRow:
    row_number: int
    source_filename: str
    raw: dict[str, Any]
    fields: dict[str, Any]
    address: NormalizedAddress
    row_hash: str


@dataclass
class PropertyParseResult:
    format: str
    headers: list[str]
    mapping: dict[str, str]
    rows: list[NormalizedPropertyRow] = field(default_factory=list)
    issues: list[PropertyParseIssue] = field(default_factory=list)

    @property
    def rejected_row_count(self) -> int:
        row_numbers = {issue.row_number for issue in self.issues if issue.row_number is not None}
        if row_numbers:
            return len(row_numbers)
        return 1 if self.issues and not self.rows else 0


def _header_key(value: object) -> str:
    text = "" if value is None else str(value).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _raw_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _cell_column(cell_ref: str) -> int:
    letters = re.match(r"[A-Za-z]+", cell_ref or "")
    if not letters:
        return 0
    result = 0
    for char in letters.group(0).upper():
        result = result * 26 + ord(char) - ord("A") + 1
    return result


def _validate_archive(
    archive: zipfile.ZipFile, *, max_members: int, max_uncompressed_bytes: int
) -> None:
    infos = archive.infolist()
    if len(infos) > max_members:
        raise ValueError("archive contains too many members")
    total_size = 0
    for info in infos:
        member = PurePosixPath(info.filename)
        if member.is_absolute() or ".." in member.parts:
            raise ValueError("archive contains an unsafe member path")
        total_size += info.file_size
        if total_size > max_uncompressed_bytes:
            raise ValueError("archive uncompressed size exceeds configured limit")


def _xlsx_rows(
    payload: bytes, *, max_archive_members: int, max_archive_uncompressed_bytes: int
) -> tuple[list[str], list[dict[str, Any]]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        _validate_archive(
            archive,
            max_members=max_archive_members,
            max_uncompressed_bytes=max_archive_uncompressed_bytes,
        )
        names = set(archive.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root.findall(".//{*}si")]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationship_root = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationships = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in relationship_root.findall("{*}Relationship")
        }
        sheet = workbook.find(".//{*}sheet")
        if sheet is None:
            raise ValueError("XLSX has no worksheet")
        relationship_id = (
            sheet.attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            or "rId1"
        )
        target = relationships.get(relationship_id, "worksheets/sheet1.xml")
        worksheet_name = target if target.startswith("xl/") else "xl/" + target.lstrip("/")
        root = ElementTree.fromstring(archive.read(worksheet_name))
        matrix: list[list[str]] = []
        for row in root.findall(".//{*}row"):
            values: list[str] = []
            for cell in row.findall("{*}c"):
                column = _cell_column(cell.attrib.get("r", ""))
                while len(values) < column - 1:
                    values.append("")
                value_node = cell.find("{*}v")
                inline = cell.find("{*}is")
                value = "" if value_node is None else "".join(value_node.itertext())
                if inline is not None:
                    value = "".join(inline.itertext())
                if cell.attrib.get("t") == "s" and value:
                    value = shared[int(value)]
                values.append(value)
            matrix.append(values)
    if not matrix:
        return [], []
    headers = [_clean(value) for value in matrix[0]]
    return headers, [
        dict(zip(headers, row + [""] * max(0, len(headers) - len(row)))) for row in matrix[1:]
    ]


def _csv_rows(payload: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    text = payload.decode("utf-8-sig", errors="strict")
    reader = csv.reader(io.StringIO(text))
    try:
        headers = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV has no header row") from exc
    headers = [_clean(value) for value in headers]
    rows: list[dict[str, Any]] = []
    for values in reader:
        if not any(_clean(value) for value in values):
            continue
        padded = values + [""] * max(0, len(headers) - len(values))
        rows.append(dict(zip(headers, padded[: len(headers)])))
    return headers, rows


def _payload_rows(
    payload: bytes,
    filename: str,
    content_type: Optional[str],
    *,
    max_archive_members: int,
    max_archive_uncompressed_bytes: int,
) -> tuple[str, list[str], list[tuple[str, dict[str, Any]]]]:
    extension = PurePosixPath(filename.lower()).suffix
    content = (content_type or "").lower()
    if extension == ".zip" or "zip" in content:
        combined_headers: list[str] = []
        combined_rows: list[tuple[str, dict[str, Any]]] = []
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            _validate_archive(
                archive,
                max_members=max_archive_members,
                max_uncompressed_bytes=max_archive_uncompressed_bytes,
            )
            members = [name for name in sorted(archive.namelist()) if not name.endswith("/")]
            supported = [
                name for name in members if PurePosixPath(name.lower()).suffix in {".csv", ".xlsx"}
            ]
            if not supported:
                raise ValueError("ZIP archive contains no supported CSV or XLSX file")
            for member in supported:
                member_payload = archive.read(member)
                member_extension = PurePosixPath(member.lower()).suffix
                headers, rows = (
                    _csv_rows(member_payload)
                    if member_extension == ".csv"
                    else _xlsx_rows(
                        member_payload,
                        max_archive_members=max_archive_members,
                        max_archive_uncompressed_bytes=max_archive_uncompressed_bytes,
                    )
                )
                member_mapping = _auto_mapping(headers)
                for canonical, _source_header in member_mapping.items():
                    if canonical not in combined_headers:
                        combined_headers.append(canonical)
                for row in rows:
                    # Keep every original header/value for provenance, while adding a stable
                    # canonical key so ZIP members with different valid spellings share one
                    # parser contract.
                    mapped_row = dict(row)
                    for canonical, source_header in member_mapping.items():
                        mapped_row.setdefault(canonical, row.get(source_header, ""))
                    combined_rows.append((member, mapped_row))
        return "zip", combined_headers, combined_rows
    if extension == ".xlsx" or "spreadsheet" in content or "excel" in content:
        headers, rows = _xlsx_rows(
            payload,
            max_archive_members=max_archive_members,
            max_archive_uncompressed_bytes=max_archive_uncompressed_bytes,
        )
        return "xlsx", headers, [(filename, row) for row in rows]
    if extension == ".csv" or "csv" in content or "text/plain" in content:
        headers, rows = _csv_rows(payload)
        return "csv", headers, [(filename, row) for row in rows]
    raise ValueError("only CSV, XLSX, and ZIP property files are supported")


def _auto_mapping(headers: list[str]) -> dict[str, str]:
    keyed = {_header_key(header): header for header in headers}
    mapping: dict[str, str] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in keyed:
                mapping[canonical] = keyed[alias]
                break
    return mapping


def _number(
    value: Any,
    field_name: str,
    issues: list[PropertyParseIssue],
    row_number: int,
    raw: dict[str, Any],
) -> Optional[float]:
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text.replace(",", "").replace("$", ""))
    except ValueError:
        issues.append(
            PropertyParseIssue(
                "invalid_number", f"{field_name} is not numeric", row_number, _raw_json(raw)
            )
        )
        return None


def _integer(
    value: Any,
    field_name: str,
    issues: list[PropertyParseIssue],
    row_number: int,
    raw: dict[str, Any],
) -> Optional[int]:
    number = _number(value, field_name, issues, row_number, raw)
    return int(number) if number is not None and number.is_integer() else None


def parse_property_file(
    payload: bytes,
    content_type: Optional[str],
    filename: str,
    mapping: Optional[dict[str, str]] = None,
    max_archive_members: int = 100,
    max_archive_uncompressed_bytes: int = 100_000_000,
) -> PropertyParseResult:
    try:
        format_name, headers, source_rows = _payload_rows(
            payload,
            filename,
            content_type,
            max_archive_members=max_archive_members,
            max_archive_uncompressed_bytes=max_archive_uncompressed_bytes,
        )
    except (ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        return PropertyParseResult(
            format="unknown",
            headers=[],
            mapping=mapping or {},
            issues=[PropertyParseIssue("parse_failed", str(exc))],
        )
    resolved_mapping = mapping or _auto_mapping(headers)
    keyed_headers = {_header_key(header) for header in headers}
    issues: list[PropertyParseIssue] = []
    missing_mapping = [field for field in PROPERTY_REQUIRED_FIELDS if field not in resolved_mapping]
    if missing_mapping:
        issues.append(
            PropertyParseIssue(
                "missing_required_mapping",
                f"required property fields are not mapped: {', '.join(missing_mapping)}",
            )
        )
    unknown_mapping = [
        f"{field}={source}"
        for field, source in resolved_mapping.items()
        if _header_key(source) not in keyed_headers
    ]
    if unknown_mapping:
        issues.append(PropertyParseIssue("mapping_source_missing", ", ".join(unknown_mapping)))
    recognized = {_header_key(source) for source in resolved_mapping.values()}
    unexpected = sorted(keyed_headers - recognized)
    if unexpected:
        issues.append(
            PropertyParseIssue(
                "unexpected_fields",
                f"unmapped source fields: {', '.join(unexpected)}",
                severity="warning",
            )
        )

    rows: list[NormalizedPropertyRow] = []
    for row_number, (source_filename, raw) in enumerate(source_rows, start=2):
        values = {field: raw.get(source, "") for field, source in resolved_mapping.items()}
        parcel_id = _clean(values.get("parcel_id"))
        address_text = _clean(values.get("address"))
        raw_payload = _raw_json({"source_file": source_filename, "row": raw})
        if not parcel_id or not address_text:
            missing = "parcel_id" if not parcel_id else "address"
            issues.append(
                PropertyParseIssue(
                    "missing_required_value", f"row is missing {missing}", row_number, raw_payload
                )
            )
            continue
        address = normalize_address(
            address_text,
            municipality=values.get("municipality"),
            postal_code=values.get("postal_code"),
            unit=values.get("unit"),
        )
        latitude = _number(values.get("latitude"), "latitude", issues, row_number, raw)
        longitude = _number(values.get("longitude"), "longitude", issues, row_number, raw)
        invalid_coordinate = False
        if latitude is not None and not -90 <= latitude <= 90:
            issues.append(
                PropertyParseIssue(
                    "invalid_coordinate",
                    "latitude is outside valid bounds",
                    row_number,
                    raw_payload,
                )
            )
            latitude = None
            invalid_coordinate = True
        if longitude is not None and not -180 <= longitude <= 180:
            issues.append(
                PropertyParseIssue(
                    "invalid_coordinate",
                    "longitude is outside valid bounds",
                    row_number,
                    raw_payload,
                )
            )
            longitude = None
            invalid_coordinate = True
        fields: dict[str, Any] = {
            "parcel_id": parcel_id,
            "situs_original": address.original,
            "normalized_address": address.normalized,
            "address_precision": address.precision,
            "address_components": address.as_dict(),
            "municipality": address.municipality,
            "postal_code": address.postal_code,
            "house_number": address.house_number,
            "street_prefix": address.street_prefix,
            "street_name": address.street_name,
            "street_type": address.street_type,
            "street_suffix": address.street_suffix,
            "unit": address.unit,
            "latitude": latitude,
            "longitude": longitude,
        }
        for field_name in FIELD_ALIASES:
            if field_name in {
                "parcel_id",
                "address",
                "municipality",
                "postal_code",
                "unit",
                "latitude",
                "longitude",
            }:
                continue
            value = values.get(field_name)
            if field_name in {
                "year_built",
                "effective_year_built",
                "number_of_buildings",
                "number_of_units",
                "stories",
            }:
                fields[field_name] = _integer(value, field_name, issues, row_number, raw)
            elif field_name in {"building_area", "living_area"}:
                fields[field_name] = _number(value, field_name, issues, row_number, raw)
            elif field_name == "geometry":
                fields[field_name] = _clean(value) or None
            else:
                fields[field_name] = _clean(value) or None
        fields["data_quality"] = {
            "address_warnings": list(address.warnings),
            "missing_coordinate": latitude is None or longitude is None,
            "invalid_coordinate": invalid_coordinate,
            "source_file": source_filename,
        }
        row_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
        rows.append(
            NormalizedPropertyRow(row_number, source_filename, raw, fields, address, row_hash)
        )
    return PropertyParseResult(format_name, headers, resolved_mapping, rows, issues)


def iter_normalized_csv_file(
    path: Path,
    *,
    mapping: Optional[dict[str, str]] = None,
    chunk_rows: int = 1000,
) -> Iterator[PropertyParseResult]:
    """Parse a normalized CSV in bounded chunks while retaining the normal parser contract.

    The HTTP importer intentionally accepts a bounded bytes payload. Real county exports can
    exceed that limit, so the operator-only manual import path uses this iterator to avoid
    materializing every source row and its geometry at once. Each yielded result has row numbers
    adjusted to the original file and uses the same normalization and validation code as the
    regular importer.
    """
    if chunk_rows < 1:
        raise ValueError("chunk_rows must be positive")
    csv.field_size_limit(max(csv.field_size_limit(), 64 * 1024 * 1024))
    filename = path.name
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        if not headers:
            yield PropertyParseResult(
                format="csv",
                headers=[],
                mapping=mapping or {},
                issues=[PropertyParseIssue("parse_failed", "CSV has no header row")],
            )
            return
        resolved_mapping = mapping or _auto_mapping(headers)
        chunk: list[dict[str, Any]] = []
        chunk_start_row = 2
        saw_data = False
        for raw in reader:
            if not any(_clean(value) for value in raw.values()):
                continue
            if not chunk:
                chunk_start_row = reader.line_num
            chunk.append(raw)
            saw_data = True
            if len(chunk) < chunk_rows:
                continue
            yield _parse_csv_chunk(
                headers,
                chunk,
                filename,
                resolved_mapping,
                chunk_start_row,
            )
            chunk = []
        if chunk:
            yield _parse_csv_chunk(
                headers,
                chunk,
                filename,
                resolved_mapping,
                chunk_start_row,
            )
        if not saw_data:
            yield parse_property_file(
                (",".join(headers) + "\n").encode("utf-8"),
                "text/csv",
                filename,
                resolved_mapping,
            )


def _parse_csv_chunk(
    headers: list[str],
    rows: list[dict[str, Any]],
    filename: str,
    mapping: dict[str, str],
    source_start_row: int,
) -> PropertyParseResult:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    parsed = parse_property_file(buffer.getvalue().encode("utf-8"), "text/csv", filename, mapping)
    row_offset = source_start_row - 2
    parsed.rows = [replace(row, row_number=row.row_number + row_offset) for row in parsed.rows]
    parsed.issues = [
        replace(issue, row_number=issue.row_number + row_offset)
        if issue.row_number is not None
        else issue
        for issue in parsed.issues
    ]
    return parsed
