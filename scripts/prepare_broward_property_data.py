#!/usr/bin/env python3
"""Build the operator-import CSV for the official Broward DOR property files.

The Florida DOR NAL and SDF files are fixed-width-schema CSV exports inside ZIP archives;
the PIN download is a shapefile archive. This command joins the three by parcel identifier,
retains the source files' hashes in every normalized row, and writes an address-matchable
CSV for ``scripts/import_sarasota_property.py``. It does not retrieve property data itself.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Iterable

try:
    import shapefile  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover - operator environment check
    raise SystemExit(
        "pyshp is required for the PIN geometry join; install with "
        "python -m pip install -e '.[property-data]'"
    ) from exc

try:
    from pyproj import Transformer  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover - operator environment check
    raise SystemExit(
        "pyproj is required to transform Broward PIN coordinates from EPSG:2881 to EPSG:4326; "
        "install with python -m pip install -e '.[property-data]'"
    ) from exc


FIELDNAMES = [
    "parcel_id",
    "address",
    "municipality",
    "postal_code",
    "county",
    "property_use_code",
    "property_use_category",
    "owner_name",
    "mailing_address",
    "year_built",
    "effective_year_built",
    "building_area",
    "living_area",
    "number_of_buildings",
    "number_of_units",
    "sales_count",
    "last_sale_date",
    "last_sale_price",
    "last_sale_legal_reference",
    "last_sale_deed_type",
    "last_sale_recording_date",
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


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _key(value: Any) -> str:
    return "".join(char for char in str(value or "").upper() if char.isalnum())


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_csv(path: Path) -> tuple[zipfile.ZipFile, io.TextIOWrapper, csv.DictReader]:
    archive = zipfile.ZipFile(path)
    members = [item for item in archive.namelist() if item.lower().endswith(".csv")]
    if len(members) != 1:
        archive.close()
        raise ValueError(f"expected exactly one CSV in {path.name}, found {len(members)}")
    handle = io.TextIOWrapper(archive.open(members[0], "r"), encoding="utf-8-sig", newline="")
    return archive, handle, csv.DictReader(handle)


def _build_sales_index(path: Path) -> tuple[dict[str, dict[str, Any]], int]:
    latest: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    archive, handle, reader = _zip_csv(path)
    try:
        for row in reader:
            parcel_id = _clean(row.get("PARCEL_ID"))
            if not parcel_id:
                continue
            counts[parcel_id] = counts.get(parcel_id, 0) + 1
            year = int(_clean(row.get("SALE_YR")) or 0)
            month = int(_clean(row.get("SALE_MO")) or 0)
            candidate = (year, month, counts[parcel_id])
            prior = latest.get(parcel_id)
            if prior is None or candidate > prior["sort_key"]:
                latest[parcel_id] = {
                    "sort_key": candidate,
                    "year": year,
                    "month": month,
                    "price": _clean(row.get("SALE_PRC")),
                    "qual_code": _clean(row.get("QUAL_CD")),
                    "legal_reference": "/".join(
                        value
                        for value in (
                            _clean(row.get("OR_BOOK")),
                            _clean(row.get("OR_PAGE")),
                            _clean(row.get("CLERK_NO")),
                        )
                        if value
                    ),
                }
    finally:
        handle.close()
        archive.close()
    for parcel_id, value in latest.items():
        value["sales_count"] = counts[parcel_id]
    return latest, sum(counts.values())


def _extract_pin(pin_zip: Path, extract_dir: Path) -> Path:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pin_zip) as archive:
        members = archive.namelist()
        shp_members = [name for name in members if name.lower().endswith(".shp")]
        if len(shp_members) != 1:
            raise ValueError(f"expected one PIN .shp member, found {len(shp_members)}")
        for name in members:
            if name.lower().endswith((".shp", ".shx", ".dbf", ".prj", ".cpg")):
                archive.extract(name, extract_dir)
        shp_path = extract_dir / shp_members[0]
    return shp_path


def _geometry_key(record: dict[str, Any]) -> str:
    for field in ("PARCELNO", "PARCEL_NO", "PARCEL_ID", "PARCELID", "STATE_PAR_ID"):
        if field in record and _clean(record[field]):
            return _key(record[field])
    return ""


def _coordinates(value: Any) -> Iterable[tuple[float, float]]:
    if (
        isinstance(value, (list, tuple))
        and len(value) >= 2
        and all(isinstance(item, (int, float)) for item in value[:2])
    ):
        yield float(value[0]), float(value[1])
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            yield from _coordinates(child)


def _transform_geometry(geometry: dict[str, Any], transformer: Transformer) -> dict[str, Any]:
    def transform(value: Any) -> Any:
        if (
            isinstance(value, (list, tuple))
            and len(value) >= 2
            and all(isinstance(item, (int, float)) for item in value[:2])
        ):
            longitude, latitude = transformer.transform(float(value[0]), float(value[1]))
            return [longitude, latitude, *value[2:]]
        if isinstance(value, list):
            return [transform(child) for child in value]
        return value

    return {**geometry, "coordinates": transform(geometry.get("coordinates"))}


def _build_geometry_index(pin_zip: Path, work_dir: Path) -> tuple[Path, int, str]:
    shp_path = _extract_pin(pin_zip, work_dir / "pin_files")
    reader = shapefile.Reader(str(shp_path))
    field_names = [field[0] for field in reader.fields[1:]]
    normalized_names = {_key(name): name for name in field_names}
    if not any(
        name in normalized_names for name in ("PARCELNO", "PARCELID", "PARCELID", "STATEPARID")
    ):
        raise ValueError(f"PIN file has no parcel identifier field; fields={field_names}")

    index_path = work_dir / "broward_pin_join.sqlite"
    if index_path.exists():
        index_path.unlink()
    connection = sqlite3.connect(index_path)
    connection.execute(
        "CREATE TABLE pin_geometry (parcel_key TEXT PRIMARY KEY, geometry TEXT NOT NULL)"
    )
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    transformer = Transformer.from_crs("EPSG:2881", "EPSG:4326", always_xy=True)
    inserted = 0
    batch: list[tuple[str, str]] = []
    for shape_record in reader.iterShapeRecords():
        record = dict(zip(field_names, shape_record.record))
        parcel_key = _geometry_key(record)
        if not parcel_key:
            continue
        geometry = json.dumps(
            _transform_geometry(shape_record.shape.__geo_interface__, transformer),
            separators=(",", ":"),
        )
        batch.append((parcel_key, geometry))
        if len(batch) >= 1000:
            connection.executemany("INSERT OR REPLACE INTO pin_geometry VALUES (?, ?)", batch)
            connection.commit()
            inserted += len(batch)
            batch = []
    if batch:
        connection.executemany("INSERT OR REPLACE INTO pin_geometry VALUES (?, ?)", batch)
        connection.commit()
        inserted += len(batch)
    connection.close()
    return (
        index_path,
        inserted,
        "https://floridarevenue.com/property/dataportal/Documents/PTO%20Data%20Portal/"
        "Map%20Data/2025F/2025F%20PIN/broward_2025pin.zip",
    )


def _representative_point(geometry: dict[str, Any]) -> tuple[str, str]:
    points = list(_coordinates(geometry.get("coordinates")))
    if not points:
        return "", ""
    return (
        f"{sum(point[1] for point in points) / len(points):.8f}",
        f"{sum(point[0] for point in points) / len(points):.8f}",
    )


def _row(
    nal: dict[str, Any],
    sale: dict[str, Any] | None,
    geometry: str | None,
    *,
    nal_hash: str,
    sdf_hash: str,
    geometry_source: str,
) -> dict[str, Any]:
    parcel_id = _clean(nal.get("PARCEL_ID"))
    address = _clean(
        " ".join(
            value for value in (_clean(nal.get("PHY_ADDR1")), _clean(nal.get("PHY_ADDR2"))) if value
        )
    )
    mailing = _clean(
        " ".join(
            value
            for value in (
                _clean(nal.get("OWN_ADDR1")),
                _clean(nal.get("OWN_ADDR2")),
                _clean(nal.get("OWN_CITY")),
                _clean(nal.get("OWN_STATE")),
                _clean(nal.get("OWN_ZIPCD")),
            )
            if value
        )
    )
    latitude = longitude = ""
    if geometry:
        try:
            latitude, longitude = _representative_point(json.loads(geometry))
        except json.JSONDecodeError:
            geometry = ""
    result = {
        "parcel_id": parcel_id,
        "address": address,
        "municipality": _clean(nal.get("PHY_CITY")),
        "postal_code": _clean(nal.get("PHY_ZIPCD")),
        "county": "Broward",
        "property_use_code": _clean(nal.get("DOR_UC")),
        "property_use_category": "",
        "owner_name": _clean(nal.get("OWN_NAME")),
        "mailing_address": mailing,
        "year_built": _clean(nal.get("ACT_YR_BLT")),
        "effective_year_built": _clean(nal.get("EFF_YR_BLT")),
        "building_area": _clean(nal.get("TOT_LVG_AREA")),
        "living_area": _clean(nal.get("TOT_LVG_AREA")),
        "number_of_buildings": _clean(nal.get("NO_BULDNG")),
        "number_of_units": _clean(nal.get("NO_RES_UNTS")),
        "sales_count": str(sale["sales_count"]) if sale else "0",
        "last_sale_date": f"{sale['year']:04d}-{sale['month']:02d}"
        if sale and sale["year"]
        else "",
        "last_sale_price": sale["price"] if sale else "",
        "last_sale_legal_reference": sale["legal_reference"] if sale else "",
        "last_sale_deed_type": sale["qual_code"] if sale else "",
        "last_sale_recording_date": f"{sale['year']:04d}-{sale['month']:02d}"
        if sale and sale["year"]
        else "",
        "total_value": _clean(nal.get("JV")),
        "land_value": _clean(nal.get("LND_VAL")),
        "building_value": _clean(nal.get("NCONST_VAL")),
        "assessed_value": _clean(nal.get("AV_SD")),
        "taxable_value": _clean(nal.get("TV_SD")),
        "latitude": latitude,
        "longitude": longitude,
        "geometry": geometry or "",
        "source_parcel_sales_sha256": sdf_hash,
        "source_detailed_sha256": nal_hash,
        "source_geometry_service": f"{geometry_source} (EPSG:2881 transformed to EPSG:4326)",
        "source_geometry_layer": "PIN",
        "source_rows": "NAL16P202501.csv;SDF16P202501.csv;Broward PIN shapefile",
    }
    return result


def prepare(nal_zip: Path, sdf_zip: Path, pin_zip: Path, output_csv: Path) -> dict[str, Any]:
    nal_hash = _hash(nal_zip)
    sdf_hash = _hash(sdf_zip)
    work_dir = output_csv.parent / "broward_pin_work"
    sales, sale_row_count = _build_sales_index(sdf_zip)
    index_path, geometry_count, geometry_source = _build_geometry_index(pin_zip, work_dir)
    connection = sqlite3.connect(index_path)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    accepted = 0
    addressed = 0
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        archive, source_handle, reader = _zip_csv(nal_zip)
        try:
            for nal in reader:
                parcel_id = _clean(nal.get("PARCEL_ID"))
                if not parcel_id:
                    continue
                key = _key(parcel_id)
                row = connection.execute(
                    "SELECT geometry FROM pin_geometry WHERE parcel_key = ?", (key,)
                ).fetchone()
                if row is None and _clean(nal.get("STATE_PAR_ID")):
                    row = connection.execute(
                        "SELECT geometry FROM pin_geometry WHERE parcel_key = ?",
                        (_key(nal.get("STATE_PAR_ID")),),
                    ).fetchone()
                geometry = row[0] if row else None
                normalized = _row(
                    nal,
                    sales.get(parcel_id),
                    geometry,
                    nal_hash=nal_hash,
                    sdf_hash=sdf_hash,
                    geometry_source=geometry_source,
                )
                writer.writerow(normalized)
                accepted += 1
                if normalized["address"]:
                    addressed += 1
        finally:
            source_handle.close()
            archive.close()
    connection.close()
    manifest = {
        "output_csv": str(output_csv),
        "nal_zip": str(nal_zip),
        "sdf_zip": str(sdf_zip),
        "pin_zip": str(pin_zip),
        "nal_sha256": nal_hash,
        "sdf_sha256": sdf_hash,
        "pin_sha256": _hash(pin_zip),
        "nal_rows_written": accepted,
        "nal_rows_with_physical_address": addressed,
        "sdf_rows_indexed": sale_row_count,
        "pin_geometries_indexed": geometry_count,
        "geometry_source": geometry_source,
    }
    output_csv.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nal", type=Path, required=True)
    parser.add_argument("--sdf", type=Path, required=True)
    parser.add_argument("--pin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.nal, args.sdf, args.pin, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
