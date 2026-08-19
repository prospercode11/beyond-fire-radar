#!/usr/bin/env python3
"""Download the public Miami-Dade parcel layer in bounded, resumable chunks.

This script uses the county's public ArcGIS REST layer only. It does not log in
to or attempt to bypass the Property Appraiser bulk-data library. The NDJSON
file retains every returned feature; the CSV is a normalized operator-import
artifact with a representative point derived from the returned polygon.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

LAYER_URL = "https://gisweb.miamidade.gov/arcgis/rest/services/Wasd/GovBound_8_v1/MapServer/0"
QUERY_URL = f"{LAYER_URL}/query"
OBJECT_ID_FIELD = "psde2.MDC.PaParcel.OBJECTID"


def _key(value: Any) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in str(value)).strip("_")


def _centroid_coordinates(value: Any) -> tuple[float | None, float | None]:
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

    visit(value)
    if not points:
        return None, None
    return (
        sum(point[1] for point in points) / len(points),
        sum(point[0] for point in points) / len(points),
    )


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _request_json(client: httpx.Client, params: dict[str, Any]) -> dict[str, Any]:
    response = client.get(QUERY_URL, params=params)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(json.dumps(payload["error"], sort_keys=True))
    return payload


def _field_map(client: httpx.Client) -> dict[str, str]:
    response = client.get(f"{LAYER_URL}?f=pjson")
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(json.dumps(payload["error"], sort_keys=True))
    result: dict[str, str] = {}
    for field in payload.get("fields", []):
        name = field.get("name")
        if name:
            result[_key(name)] = name
            result[_key(field.get("alias", ""))] = name
    return result


def _attribute(properties: dict[str, Any], fields: dict[str, str], *aliases: str) -> Any:
    for alias in aliases:
        source_name = fields.get(_key(alias))
        value = properties.get(source_name) if source_name else None
        if value not in (None, ""):
            return value
    return ""


def _normalized_row(
    feature: dict[str, Any], fields: dict[str, str], *, source_hash: str
) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    latitude, longitude = _centroid_coordinates(geometry.get("coordinates"))
    condo = str(_attribute(properties, fields, "CONDO FLAG")).strip().upper()
    normalized: dict[str, Any] = {
        "parcel_id": _attribute(properties, fields, "PID", "FOLIO"),
        "address": _attribute(properties, fields, "SITE ADDRESS", "SITE ADDR NO UNIT"),
        "municipality": _attribute(properties, fields, "SITE CITY"),
        "postal_code": _attribute(properties, fields, "SITE ZIP CODE"),
        "unit": _attribute(properties, fields, "SITE UNIT"),
        "owner_name": _attribute(properties, fields, "OWNER1"),
        "mailing_address": " ".join(
            str(_attribute(properties, fields, alias)).strip()
            for alias in ("MAILING ADDR1", "MAILING ADDR2", "MAILING ADDR3")
            if _attribute(properties, fields, alias) not in (None, "")
        ),
        "property_use_category": "condominium" if condo in {"Y", "YES", "1", "TRUE"} else "",
        "year_built": _attribute(properties, fields, "YEAR BUILT"),
        "building_area": _attribute(properties, fields, "BUILDING ACTUAL AREA"),
        "number_of_buildings": _attribute(properties, fields, "BUILDING COUNT"),
        "number_of_units": _attribute(properties, fields, "UNIT COUNT"),
        "stories": _attribute(properties, fields, "FLOOR COUNT"),
        "bedrooms": _attribute(properties, fields, "BEDROOM COUNT"),
        "rooms": _attribute(properties, fields, "ROOM COUNT"),
        "latitude": latitude,
        "longitude": longitude,
        "county": "Miami-Dade",
        "geometry": json.dumps(geometry, ensure_ascii=False, separators=(",", ":")),
        "source_geometry_service": LAYER_URL,
        "source_geometry_layer": "0",
        "source_parcel_gis_sha256": source_hash,
    }
    return normalized


def download(
    output_dir: Path, *, chunk_size: int, limit: int | None, resume: bool
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ndjson_path = output_dir / "miami_dade_parcel_gis.ndjson"
    csv_path = output_dir / "miami_dade_parcel_import.csv"
    manifest_path = output_dir / "manifest.json"
    manifest: dict[str, Any] = {
        "source_url": LAYER_URL,
        "query_url": QUERY_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "geometry_format": "GeoJSON, EPSG:4326",
        "chunk_size": chunk_size,
        "limit": limit,
        "complete": False,
        "feature_count": 0,
        "normalized_row_count": 0,
        "rejected_row_count": 0,
        "completed_chunks": 0,
    }
    if resume and manifest_path.exists():
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        if prior.get("complete"):
            return prior
        manifest.update(prior)

    mode = "ab" if resume and ndjson_path.exists() else "wb"
    csv_mode = "a" if resume and csv_path.exists() else "w"
    existing_chunks = int(manifest.get("completed_chunks", 0))
    with httpx.Client(follow_redirects=True, timeout=90.0) as client:
        fields = _field_map(client)
        ids_payload = _request_json(
            client,
            {"where": "1=1", "returnIdsOnly": "true", "f": "json"},
        )
        object_ids = sorted(int(value) for value in ids_payload.get("objectIds", []))
        if limit is not None:
            object_ids = object_ids[:limit]
        manifest["object_id_count"] = len(object_ids)
        ndjson_file = ndjson_path.open(mode)
        csv_file = csv_path.open(csv_mode, newline="", encoding="utf-8")
        csv_writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "parcel_id",
                "address",
                "municipality",
                "postal_code",
                "unit",
                "owner_name",
                "mailing_address",
                "property_use_category",
                "year_built",
                "building_area",
                "number_of_buildings",
                "number_of_units",
                "stories",
                "bedrooms",
                "rooms",
                "latitude",
                "longitude",
                "county",
                "geometry",
                "source_geometry_service",
                "source_geometry_layer",
                "source_parcel_gis_sha256",
            ],
        )
        if csv_mode == "w":
            csv_writer.writeheader()
        try:
            chunks = [
                (chunk_index, object_ids[start : start + chunk_size])
                for chunk_index, start in enumerate(range(0, len(object_ids), chunk_size))
                if chunk_index >= existing_chunks
            ]
            total_chunks = (len(object_ids) + chunk_size - 1) // chunk_size
            with ThreadPoolExecutor(max_workers=6) as executor:
                for batch_start in range(0, len(chunks), 6):
                    batch = chunks[batch_start : batch_start + 6]
                    futures = {
                        chunk_index: executor.submit(
                            _request_json,
                            client,
                            {
                                "where": (
                                    f"{OBJECT_ID_FIELD} >= {chunk_ids[0]} AND "
                                    f"{OBJECT_ID_FIELD} <= {chunk_ids[-1]}"
                                ),
                                "outFields": "*",
                                "returnGeometry": "true",
                                "outSR": "4326",
                                "f": "geojson",
                            },
                        )
                        for chunk_index, chunk_ids in batch
                    }
                    for chunk_index, _chunk_ids in batch:
                        payload = futures[chunk_index].result()
                        features = payload.get("features", [])
                        for feature in features:
                            raw_line = json.dumps(
                                feature, ensure_ascii=False, separators=(",", ":")
                            )
                            ndjson_file.write((raw_line + "\n").encode("utf-8"))
                            source_hash = hashlib.sha256(raw_line.encode("utf-8")).hexdigest()
                            normalized = _normalized_row(feature, fields, source_hash=source_hash)
                            if normalized["parcel_id"] and normalized["address"]:
                                csv_writer.writerow(normalized)
                                manifest["normalized_row_count"] += 1
                            else:
                                manifest["rejected_row_count"] += 1
                            manifest["feature_count"] += 1
                        manifest["completed_chunks"] = chunk_index + 1
                        ndjson_file.flush()
                        csv_file.flush()
                        _write_manifest(manifest_path, manifest)
                        print(
                            f"chunk {chunk_index + 1}/{total_chunks}: "
                            f"{manifest['feature_count']}/{len(object_ids)} features",
                            flush=True,
                        )
        finally:
            ndjson_file.close()
            csv_file.close()
    manifest["complete"] = manifest["feature_count"] == len(object_ids)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    for path, key in ((ndjson_path, "ndjson_sha256"), (csv_path, "csv_sha256")):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        manifest[key] = digest.hexdigest()
    _write_manifest(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw-snapshots/miami_dade_property_gis"),
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="ArcGIS object-id range size; the service caps returned records at 1,000",
    )
    parser.add_argument("--limit", type=int, default=None, help="bounded test download")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    if args.chunk_size < 1 or args.chunk_size > 1000:
        parser.error("--chunk-size must be between 1 and 1000")
    try:
        manifest = download(
            args.output_dir,
            chunk_size=args.chunk_size,
            limit=args.limit,
            resume=not args.no_resume,
        )
    except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
        print(f"download failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
