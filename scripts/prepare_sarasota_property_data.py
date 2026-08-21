#!/usr/bin/env python3
"""Build the operator-import CSV for the official Sarasota SCPA property files.

The SCPA parcel/sales archive supplies tax-roll attributes and sales history, the detailed
archive supplies per-building characteristics, and the county parcel ArcGIS layer supplies
geometry. This command joins the three by parcel account, retains every source hash in each
normalized row, and writes an address-matchable CSV for
``scripts/import_sarasota_property.py``. Attribute data is never retrieved automatically: the
two archives must already be operator-downloaded files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import httpx

LAYER_URL = (
    "https://services3.arcgis.com/icrWMv7eBkctFu1f"
    "/arcgis/rest/services/ParcelHosted/FeatureServer/0"
)
LAYER_NAME = "ParcelHosted/0"
PARCEL_MEMBER = "Parcel_Sales_CSV/Sarasota.csv"
SALES_MEMBER = "Parcel_Sales_CSV/ParcelSales.csv"
BUILDING_MEMBER = "Building.txt"
PLACEHOLDER_HOUSE_NUMBERS = {"0", "00", "000", "0000"}

FIELDNAMES = [
    "parcel_id",
    "address",
    "address_alias",
    "house_number",
    "street_prefix",
    "street_name",
    "unit",
    "municipality",
    "postal_code",
    "county",
    "property_use_code",
    "owner_name",
    "mailing_address",
    "year_built",
    "effective_year_built",
    "stories",
    "building_area",
    "living_area",
    "number_of_buildings",
    "number_of_units",
    "sales_count",
    "last_sale_date",
    "last_sale_price",
    "last_sale_legal_reference",
    "last_sale_deed_type",
    "total_value",
    "land_value",
    "building_value",
    "assessed_value",
    "taxable_value",
    "latitude",
    "longitude",
    "geometry",
    "source_parcel_sales_sha256",
    "source_detailed_sha256",
    "source_geometry_service",
    "source_geometry_layer",
    "source_rows",
]

CACHE_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS geometry (
    account TEXT PRIMARY KEY,
    full_address TEXT,
    latitude TEXT,
    longitude TEXT,
    geojson TEXT
);
CREATE TABLE IF NOT EXISTS geometry_progress (upper_object_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS sales (
    account TEXT PRIMARY KEY,
    sales_count INTEGER,
    last_date TEXT,
    last_price TEXT,
    last_reference TEXT,
    last_deed_type TEXT
);
CREATE TABLE IF NOT EXISTS building (
    account TEXT PRIMARY KEY,
    card_count INTEGER,
    effective_year_built TEXT,
    stories TEXT
);
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any) -> str:
    text = _clean(value).replace(",", "")
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return ""
    return str(int(number)) if number.is_integer() else str(number)


def _iso_date(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return ""


def _representative_point(geometry: dict[str, Any]) -> tuple[str, str]:
    points: list[tuple[float, float]] = []

    def visit(node: Any) -> None:
        if (
            isinstance(node, list)
            and len(node) >= 2
            and all(isinstance(item, (int, float)) for item in node[:2])
        ):
            points.append((float(node[0]), float(node[1])))
            return
        if isinstance(node, list):
            for child in node:
                visit(child)

    visit(geometry.get("coordinates"))
    if not points:
        return "", ""
    longitude = sum(point[0] for point in points) / len(points)
    latitude = sum(point[1] for point in points) / len(points)
    return f"{latitude:.7f}", f"{longitude:.7f}"


def _open_cache(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    cache = sqlite3.connect(path)
    cache.executescript(CACHE_SCHEMA)
    return cache


def _layer_bounds(client: httpx.Client, layer_url: str) -> tuple[int, int]:
    statistics = [
        {
            "statisticType": "min",
            "onStatisticField": "OBJECTID",
            "outStatisticFieldName": "lo",
        },
        {
            "statisticType": "max",
            "onStatisticField": "OBJECTID",
            "outStatisticFieldName": "hi",
        },
    ]
    response = client.get(
        f"{layer_url}/query",
        params={"where": "1=1", "outStatistics": json.dumps(statistics), "f": "json"},
        timeout=120,
    )
    response.raise_for_status()
    attributes = response.json()["features"][0]["attributes"]
    return int(attributes["lo"]), int(attributes["hi"])


def _fetch_window(
    client: httpx.Client, layer_url: str, start: int, end: int
) -> dict[str, Any]:
    parameters = {
        "where": f"OBJECTID >= {start} AND OBJECTID <= {end}",
        "outFields": "ACCOUNT,FULLADDRESS",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "6",
        "f": "geojson",
    }
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = client.get(f"{layer_url}/query", params=parameters, timeout=180)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as error:
            last_error = error
            if attempt == 3:
                break
    raise RuntimeError(f"geometry window {start}-{end} failed: {last_error}")


def _download_geometry(cache: sqlite3.Connection, layer_url: str, chunk_size: int) -> int:
    with httpx.Client(headers={"User-Agent": "beyond-fire-radar-operator-import"}) as client:
        low, high = _layer_bounds(client, layer_url)
        done = {row[0] for row in cache.execute("SELECT upper_object_id FROM geometry_progress")}
        windows = [
            (start, min(start + chunk_size - 1, high)) for start in range(low, high + 1, chunk_size)
        ]
        pending = [window for window in windows if window[1] not in done]
        print(f"geometry: {len(windows) - len(pending)}/{len(windows)} windows already cached")
        for index, (start, end) in enumerate(pending, start=1):
            payload = _fetch_window(client, layer_url, start, end)
            rows = []
            for feature in payload.get("features", []):
                properties = feature.get("properties") or {}
                account = _clean(properties.get("ACCOUNT"))
                if not account:
                    continue
                geometry = feature.get("geometry")
                latitude = longitude = ""
                geojson = ""
                if isinstance(geometry, dict) and geometry.get("type") in {
                    "Polygon",
                    "MultiPolygon",
                }:
                    latitude, longitude = _representative_point(geometry)
                    geojson = json.dumps(geometry, separators=(",", ":"))
                rows.append(
                    (account, _clean(properties.get("FULLADDRESS")), latitude, longitude, geojson)
                )
            cache.executemany(
                "INSERT OR REPLACE INTO geometry"
                " (account, full_address, latitude, longitude, geojson) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            cache.execute(
                "INSERT OR REPLACE INTO geometry_progress (upper_object_id) VALUES (?)", (end,)
            )
            cache.commit()
            if index % 10 == 0 or index == len(pending):
                total = cache.execute("SELECT COUNT(*) FROM geometry").fetchone()[0]
                print(f"geometry: window {index}/{len(pending)}; {total:,} parcels cached")
    return cache.execute("SELECT COUNT(*) FROM geometry").fetchone()[0]


def _member_reader(archive: zipfile.ZipFile, member: str) -> Iterator[dict[str, str]]:
    with archive.open(member) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))


def _load_sales(cache: sqlite3.Connection, parcels_zip: Path) -> int:
    existing = cache.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    if existing:
        print(f"sales: {existing:,} accounts already aggregated")
        return existing
    latest: dict[str, tuple[int, str, str, str, str]] = {}
    with zipfile.ZipFile(parcels_zip) as archive:
        for count, row in enumerate(_member_reader(archive, SALES_MEMBER), start=1):
            account = _clean(row.get("Account"))
            if not account:
                continue
            date = _iso_date(row.get("SaleDate"))
            previous = latest.get(account)
            total = (previous[0] if previous else 0) + 1
            if previous and previous[1] >= date:
                latest[account] = (total, previous[1], previous[2], previous[3], previous[4])
            else:
                latest[account] = (
                    total,
                    date,
                    _number(row.get("SalePrice")),
                    _clean(row.get("LegalReference")),
                    _clean(row.get("DeedType")),
                )
            if count % 500_000 == 0:
                print(f"sales: {count:,} rows scanned")
    cache.executemany(
        "INSERT OR REPLACE INTO sales"
        " (account, sales_count, last_date, last_price, last_reference, last_deed_type)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [(account, *values) for account, values in latest.items()],
    )
    cache.commit()
    print(f"sales: {len(latest):,} accounts aggregated")
    return len(latest)


def _load_buildings(cache: sqlite3.Connection, detailed_zip: Path) -> int:
    existing = cache.execute("SELECT COUNT(*) FROM building").fetchone()[0]
    if existing:
        print(f"building: {existing:,} accounts already aggregated")
        return existing
    summary: dict[str, tuple[int, str, str]] = {}
    with zipfile.ZipFile(detailed_zip) as archive:
        for count, row in enumerate(_member_reader(archive, BUILDING_MEMBER), start=1):
            account = _clean(row.get("parcelid"))
            if not account:
                continue
            previous = summary.get(account)
            cards = (previous[0] if previous else 0) + 1
            effective = previous[1] if previous and previous[1] else _number(row.get("effyearblt"))
            stories = previous[2] if previous and previous[2] else _number(row.get("storyhgt"))
            summary[account] = (cards, effective, stories)
            if count % 500_000 == 0:
                print(f"building: {count:,} rows scanned")
    cache.executemany(
        "INSERT OR REPLACE INTO building (account, card_count, effective_year_built, stories)"
        " VALUES (?, ?, ?, ?)",
        [(account, *values) for account, values in summary.items()],
    )
    cache.commit()
    print(f"building: {len(summary):,} accounts aggregated")
    return len(summary)


def _mailing_address(row: dict[str, str]) -> str:
    lines = [
        _clean(row.get(key)) for key in ("NAME_ADD2", "NAME_ADD3", "NAME_ADD4", "NAME_ADD5")
    ]
    locality = " ".join(
        part
        for part in (_clean(row.get("CITY")), _clean(row.get("STATE")), _clean(row.get("ZIP")))
        if part
    )
    parts = [line for line in lines if line]
    if locality:
        parts.append(locality)
    return ", ".join(parts)


def _situs_address(row: dict[str, str]) -> str:
    house = _clean(row.get("LOCN"))
    if house in PLACEHOLDER_HOUSE_NUMBERS:
        house = ""
    address = " ".join(
        part for part in (house, _clean(row.get("LOCD")), _clean(row.get("LOCS"))) if part
    )
    unit = _clean(row.get("UNIT"))
    return f"{address} {unit}".strip() if unit else address


def write_normalized_csv(
    parcels_zip: Path,
    output: Path,
    cache: sqlite3.Connection,
    layer_url: str,
    parcels_hash: str,
    detailed_hash: str,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped_without_address = 0
    rows_with_geometry = 0
    with zipfile.ZipFile(parcels_zip) as archive:
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            for count, row in enumerate(_member_reader(archive, PARCEL_MEMBER), start=1):
                account = _clean(row.get("ACCOUNT"))
                if not account:
                    continue
                geometry_row = cache.execute(
                    "SELECT full_address, latitude, longitude, geojson"
                    " FROM geometry WHERE account = ?",
                    (account,),
                ).fetchone()
                full_address, latitude, longitude, geojson = geometry_row or ("", "", "", "")
                address = _situs_address(row) or _clean(full_address)
                if not address:
                    skipped_without_address += 1
                    continue
                if geojson:
                    rows_with_geometry += 1
                sales_row = cache.execute(
                    "SELECT sales_count, last_date, last_price, last_reference, last_deed_type"
                    " FROM sales WHERE account = ?",
                    (account,),
                ).fetchone()
                sales_count, last_date, last_price, last_reference, last_deed = sales_row or (
                    "",
                    "",
                    "",
                    "",
                    "",
                )
                building_row = cache.execute(
                    "SELECT card_count, effective_year_built, stories FROM building"
                    " WHERE account = ?",
                    (account,),
                ).fetchone()
                card_count, effective_year, stories = building_row or ("", "", "")
                writer.writerow(
                    {
                        "parcel_id": account,
                        "address": address,
                        "address_alias": _clean(full_address),
                        "house_number": _clean(row.get("LOCN")),
                        "street_prefix": _clean(row.get("LOCD")),
                        "street_name": _clean(row.get("LOCS")),
                        "unit": _clean(row.get("UNIT")),
                        "municipality": _clean(row.get("LOCCITY"))
                        or _clean(row.get("Municipality")),
                        "postal_code": _clean(row.get("LOCZIP")),
                        "county": "Sarasota",
                        "property_use_code": _clean(row.get("STCD")),
                        "owner_name": _clean(row.get("NAME1")),
                        "mailing_address": _mailing_address(row),
                        "year_built": _number(row.get("YRBL")),
                        "effective_year_built": effective_year or "",
                        "stories": stories or "",
                        "building_area": _number(row.get("GRND_AREA")),
                        "living_area": _number(row.get("LIVING")),
                        "number_of_buildings": str(card_count) if card_count else "",
                        "number_of_units": _number(row.get("LIVUNITS")),
                        "sales_count": str(sales_count) if sales_count else "",
                        "last_sale_date": last_date or _iso_date(row.get("SALE_DATE")),
                        "last_sale_price": last_price or _number(row.get("SALE_AMT")),
                        "last_sale_legal_reference": last_reference or _clean(row.get("LEGALREFER")),
                        "last_sale_deed_type": last_deed or "",
                        "total_value": _number(row.get("JUST")),
                        "land_value": _number(row.get("LNVS_N")),
                        "building_value": _number(row.get("IMPROVEMT")),
                        "assessed_value": _number(row.get("ASSD")),
                        "taxable_value": _number(row.get("TXBL")),
                        "latitude": latitude or "",
                        "longitude": longitude or "",
                        "geometry": geojson or "",
                        "source_parcel_sales_sha256": parcels_hash,
                        "source_detailed_sha256": detailed_hash,
                        "source_geometry_service": layer_url,
                        "source_geometry_layer": LAYER_NAME,
                        "source_rows": "1",
                    }
                )
                written += 1
                if count % 100_000 == 0:
                    print(f"normalize: {count:,} parcel rows scanned; {written:,} written")
    return {
        "normalized_row_count": written,
        "skipped_without_address": skipped_without_address,
        "rows_with_geometry": rows_with_geometry,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parcels-zip", type=Path, required=True)
    parser.add_argument("--detailed-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--layer-url", default=LAYER_URL)
    parser.add_argument("--chunk-size", type=int, default=2000)
    parser.add_argument("--skip-geometry", action="store_true")
    args = parser.parse_args()
    if args.chunk_size < 1 or args.chunk_size > 2000:
        parser.error("--chunk-size must be between 1 and 2000")

    cache_path = args.cache or args.output.with_suffix(".cache.sqlite")
    cache = _open_cache(cache_path)
    try:
        print("hashing source archives")
        parcels_hash = _sha256(args.parcels_zip)
        detailed_hash = _sha256(args.detailed_zip)
        if args.skip_geometry:
            geometry_count = cache.execute("SELECT COUNT(*) FROM geometry").fetchone()[0]
        else:
            geometry_count = _download_geometry(cache, args.layer_url, args.chunk_size)
        _load_sales(cache, args.parcels_zip)
        _load_buildings(cache, args.detailed_zip)
        report = write_normalized_csv(
            args.parcels_zip,
            args.output,
            cache,
            args.layer_url,
            parcels_hash,
            detailed_hash,
        )
    finally:
        cache.close()

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output": str(args.output),
        "output_sha256": _sha256(args.output),
        "geometry_parcel_count": geometry_count,
        "source_geometry_service": args.layer_url,
        "source_geometry_layer": LAYER_NAME,
        "source_parcel_sales_sha256": parcels_hash,
        "source_detailed_sha256": detailed_hash,
        **report,
    }
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
