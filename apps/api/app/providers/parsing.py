from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from app.providers.taxonomy import classify_event

PARSER_VERSION = "sarasota.dispatch.v1"
SCHEMA_VERSION = "sarasota.dispatch.schema.v1"
SUPPORTED_FORMATS = {"csv", "html", "json"}
EXPECTED_FIELDS = [
    "date",
    "time",
    "event_type",
    "location",
    "grid",
    "zone",
    "source_case_number",
    "source_event_id",
    "latitude",
    "longitude",
]
REQUIRED_FIELDS = ["time", "event_type", "location"]
LOCAL_TIMEZONE = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class ParseIssue:
    code: str
    message: str
    row_number: Optional[int] = None
    raw_payload: Optional[str] = None


@dataclass(frozen=True)
class SchemaAssessment:
    observed_fields: List[str]
    missing_required_fields: List[str]
    unexpected_fields: List[str]
    severity: str
    code: Optional[str]
    message: Optional[str]


@dataclass(frozen=True)
class ParsedDispatchRow:
    row_number: int
    source_record_id: str
    source_event_id: Optional[str]
    source_case_number: Optional[str]
    event_time: Optional[datetime]
    original_event_type: str
    normalized_event_family: str
    original_location: str
    location_precision: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    grid: Optional[str]
    agency: Optional[str]
    station: Optional[str]
    raw_payload: Dict[str, Any]
    parser_confidence: float


@dataclass
class ParseResult:
    format: str
    parser_version: str
    schema_version: str
    rows: List[ParsedDispatchRow] = field(default_factory=list)
    issues: List[ParseIssue] = field(default_factory=list)
    schema: Optional[SchemaAssessment] = None

    @property
    def zero_row_anomaly(self) -> bool:
        return not self.rows and not any(
            issue.code == "unsupported_format" for issue in self.issues
        )


class DispatchParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _header_key(value: str) -> str:
    value = _clean(value).lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value or "unnamed"


def _unique_headers(headers: Sequence[str]) -> List[str]:
    counts: Dict[str, int] = {}
    result: List[str] = []
    for raw_header in headers:
        base = _header_key(raw_header)
        counts[base] = counts.get(base, 0) + 1
        result.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return result


def _canonical_header(field_name: str) -> Optional[str]:
    key = _header_key(field_name)
    if key in {"date", "event_date", "incident_date", "_group_date"}:
        return "date"
    if key in {"time", "event_time", "event_datetime", "datetime", "timestamp", "incident_time"}:
        return "time"
    if key in {"event", "event_type", "incident_type", "call_type", "nature"}:
        return "event_type"
    if key.startswith("event_") and key.split("_")[-1].isdigit():
        return "source_event_id"
    if key in {"event_id", "source_event_id", "shared_event_number", "shared_event", "fr_event"}:
        return "source_event_id"
    if key in {"location", "address", "incident_location", "situs"}:
        return "location"
    if key in {"latitude", "lat", "y", "y_coordinate"}:
        return "latitude"
    if key in {"longitude", "lon", "lng", "long", "x", "x_coordinate"}:
        return "longitude"
    if key in {"location_precision", "address_precision", "geocode_precision"}:
        return "location_precision"
    if key in {"grid", "dispatch_grid"}:
        return "grid"
    if key in {"zone", "station", "responding_station", "agency_station"}:
        return "zone"
    if key in {"case", "case_number", "case_num", "agency_case_number", "source_case_number"}:
        return "source_case_number"
    if key == "event_2":
        return "source_event_id"
    return None


def _parse_date(value: str) -> Optional[date]:
    value = _clean(value)
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_event_time(raw: Dict[str, Any]) -> Optional[datetime]:
    explicit = _clean(
        raw.get("event_datetime")
        or raw.get("datetime")
        or raw.get("timestamp")
        or (raw.get("event_time") if "T" in _clean(raw.get("event_time")) else "")
    )
    if explicit:
        normalized = explicit.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=LOCAL_TIMEZONE).astimezone(timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass

    event_date = _parse_date(
        _clean(raw.get("date") or raw.get("event_date") or raw.get("_group_date"))
    )
    event_time = _clean(raw.get("time") or raw.get("event_time"))
    if event_date is None or not event_time:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p"):
        try:
            parsed_time = datetime.strptime(event_time, fmt).time()
            local = datetime.combine(event_date, parsed_time).replace(tzinfo=LOCAL_TIMEZONE)
            return local.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _zone_parts(zone: str) -> Tuple[Optional[str], Optional[str]]:
    station = _clean(zone) or None
    if not station:
        return None, None
    if " STA " in station:
        return station.split(" STA ", 1)[0].strip() or None, station
    if " - " in station:
        return station.split(" - ", 1)[0].strip() or None, station
    return station, station


def _coordinate(raw: Any, *, minimum: float, maximum: float) -> Optional[float]:
    value = _clean(raw)
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if minimum <= parsed <= maximum else None


def _value(raw: Dict[str, Any], aliases: Sequence[str]) -> str:
    for alias in aliases:
        value = _clean(raw.get(alias))
        if value:
            return value
    return ""


def _canonicalize(raw: Dict[str, Any], row_number: int) -> ParsedDispatchRow:
    original_event = _value(raw, ("event_type", "event", "incident_type", "call_type"))
    location = _value(raw, ("location", "address", "incident_location"))
    if not original_event:
        raise DispatchParseError("missing_event_type", "row has no event type")
    if not location:
        raise DispatchParseError("missing_location", "row has no location")

    source_event_id = (
        _value(raw, ("source_event_id", "event_id", "event_2", "shared_event_number")) or None
    )
    source_case_number = (
        _value(raw, ("source_case_number", "case", "case_number", "case_num")) or None
    )
    stable_key = "|".join(
        value or ""
        for value in (
            source_case_number,
            source_event_id,
            _clean(raw.get("date")),
            _clean(raw.get("time")),
            location,
            original_event,
        )
    )
    source_record_id = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:32]
    event_time = _parse_event_time(raw)
    agency, station = _zone_parts(_value(raw, ("zone", "station", "responding_station")))
    normalized_event = classify_event(original_event)
    confidence = 1.0 if event_time is not None else 0.7
    latitude = _coordinate(raw.get("latitude") or raw.get("lat"), minimum=-90.0, maximum=90.0)
    longitude = _coordinate(
        raw.get("longitude") or raw.get("lon") or raw.get("lng"), minimum=-180.0, maximum=180.0
    )
    return ParsedDispatchRow(
        row_number=row_number,
        source_record_id=source_record_id,
        source_event_id=source_event_id,
        source_case_number=source_case_number,
        event_time=event_time,
        original_event_type=original_event,
        normalized_event_family=normalized_event,
        original_location=location,
        location_precision=_value(raw, ("location_precision", "address_precision")) or None,
        latitude=latitude,
        longitude=longitude,
        grid=_value(raw, ("grid", "dispatch_grid")) or None,
        agency=agency,
        station=station,
        raw_payload=raw,
        parser_confidence=confidence,
    )


def _schema(fields: Sequence[str]) -> SchemaAssessment:
    canonical_fields = sorted({mapped for field in fields if (mapped := _canonical_header(field))})
    missing = sorted(set(REQUIRED_FIELDS) - set(canonical_fields))
    unexpected = sorted(
        {
            _header_key(field)
            for field in fields
            if _canonical_header(field) is None and _header_key(field) != "unnamed"
        }
    )
    if missing:
        severity, code = "error", "missing_required_fields"
        message = f"required dispatch fields are missing: {', '.join(missing)}"
    elif unexpected:
        severity, code = "warning", "unexpected_fields"
        message = f"unrecognized dispatch fields are present: {', '.join(unexpected)}"
    else:
        severity, code, message = "info", None, None
    return SchemaAssessment(
        observed_fields=canonical_fields,
        missing_required_fields=missing,
        unexpected_fields=unexpected,
        severity=severity,
        code=code,
        message=message,
    )


class _SarasotaTableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_dispatch_table = False
        self.in_thead = False
        self.current_row: Optional[List[str]] = None
        self.current_row_is_group = False
        self.current_cell: Optional[List[str]] = None
        self.current_cell_is_group = False
        self.current_row_class = ""
        self.headers: List[str] = []
        self.rows: List[Tuple[Optional[str], List[str]]] = []
        self.group_date: Optional[str] = None
        self._group_aria: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "table" and (
            "dispatch" in attr_map.get("aria-label", "").lower()
            or "mud-table-root" in attr_map.get("class", "")
        ):
            self.in_dispatch_table = True
        if not self.in_dispatch_table:
            return
        if tag == "thead":
            self.in_thead = True
        elif tag == "tr":
            self.current_row = []
            self.current_row_class = attr_map.get("class", "")
            self.current_row_is_group = False
        elif tag in {"th", "td"} and self.current_row is not None:
            self.current_cell = []
            self.current_cell_is_group = "custom-group" in attr_map.get("class", "")
            self._group_aria = attr_map.get("aria-label")

    def handle_endtag(self, tag: str) -> None:
        if not self.in_dispatch_table:
            return
        if tag in {"th", "td"} and self.current_cell is not None and self.current_row is not None:
            value = _clean(" ".join(self.current_cell))
            self.current_row.append(value)
            if self.current_cell_is_group:
                self.current_row_is_group = True
                match = re.search(r"by (\d{1,2}/\d{1,2}/\d{2,4})", self._group_aria or "")
                self.group_date = (
                    match.group(1) if match else value.replace("Event Date:", "").strip()
                )
            self.current_cell = None
            self._group_aria = None
        elif tag == "tr" and self.current_row is not None:
            if self.current_row_is_group:
                pass
            elif self.in_thead:
                self.headers = _unique_headers(self.current_row)
            elif self.current_row:
                self.rows.append((self.group_date, self.current_row))
            self.current_row = None
        elif tag == "thead":
            self.in_thead = False
        elif tag == "table":
            self.in_dispatch_table = False

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(data)


def _html_rows(payload: bytes) -> Tuple[List[str], List[Dict[str, Any]]]:
    parser = _SarasotaTableHTMLParser()
    parser.feed(payload.decode("utf-8-sig", errors="replace"))
    if not parser.headers:
        raise DispatchParseError(
            "dispatch_table_missing", "HTML did not contain a dispatch table header"
        )
    if not parser.rows:
        return parser.headers, []
    rows: List[Dict[str, Any]] = []
    for group_date, values in parser.rows:
        padded = list(values) + [""] * max(0, len(parser.headers) - len(values))
        raw = dict(zip(parser.headers, padded[: len(parser.headers)]))
        if group_date:
            raw["_group_date"] = group_date
        rows.append(raw)
    return parser.headers, rows


def _csv_rows(payload: bytes) -> Tuple[List[str], List[Dict[str, Any]]]:
    text = payload.decode("utf-8-sig", errors="strict")
    reader = csv.reader(io.StringIO(text))
    try:
        headers_raw = next(reader)
    except StopIteration as exc:
        raise DispatchParseError("empty_snapshot", "CSV snapshot has no header row") from exc
    headers = _unique_headers(headers_raw)
    rows: List[Dict[str, Any]] = []
    for values in reader:
        if not any(_clean(value) for value in values):
            continue
        padded = list(values) + [""] * max(0, len(headers) - len(values))
        rows.append(dict(zip(headers, padded[: len(headers)])))
    return headers, rows


def _json_rows(payload: bytes) -> Tuple[List[str], List[Dict[str, Any]]]:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DispatchParseError("invalid_json", "JSON snapshot could not be decoded") from exc
    records = decoded.get("records") if isinstance(decoded, dict) else decoded
    if not isinstance(records, list):
        raise DispatchParseError("invalid_json_shape", "JSON snapshot must contain a records list")
    rows = [record for record in records if isinstance(record, dict)]
    headers = sorted({key for row in rows for key in row.keys()})
    return headers, rows


def parse_snapshot(
    payload: bytes,
    content_type: Optional[str],
    filename: str,
    parser_version: str = PARSER_VERSION,
) -> ParseResult:
    if parser_version != PARSER_VERSION:
        raise DispatchParseError(
            "unsupported_parser_version", f"parser version {parser_version} is not registered"
        )
    lower_name = filename.lower()
    if lower_name.endswith((".html", ".htm")) or "html" in (content_type or "").lower():
        format_name = "html"
        row_loader = _html_rows
    elif lower_name.endswith(".json") or "json" in (content_type or "").lower():
        format_name = "json"
        row_loader = _json_rows
    elif lower_name.endswith(".csv") or "csv" in (content_type or "").lower():
        format_name = "csv"
        row_loader = _csv_rows
    else:
        return ParseResult(
            format="unknown",
            parser_version=parser_version,
            schema_version=SCHEMA_VERSION,
            issues=[
                ParseIssue("unsupported_format", "only CSV, HTML, and JSON snapshots are supported")
            ],
        )

    headers, raw_rows = row_loader(payload)
    assessment = _schema(headers)
    result = ParseResult(
        format=format_name,
        parser_version=parser_version,
        schema_version=SCHEMA_VERSION,
        schema=assessment,
    )
    if assessment.missing_required_fields:
        result.issues.append(
            ParseIssue("schema_drift", assessment.message or "required fields are missing")
        )
    elif assessment.unexpected_fields:
        result.issues.append(
            ParseIssue("schema_warning", assessment.message or "unexpected fields are present")
        )

    for row_number, raw in enumerate(raw_rows, start=2):
        raw_payload = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
        try:
            result.rows.append(_canonicalize(raw, row_number))
        except DispatchParseError as exc:
            result.issues.append(ParseIssue(exc.code, str(exc), row_number, raw_payload))
    if not raw_rows:
        result.issues.append(
            ParseIssue(
                "zero_row_anomaly", "snapshot parsed successfully but contained zero data rows"
            )
        )
    return result
