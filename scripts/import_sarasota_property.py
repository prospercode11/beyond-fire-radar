#!/usr/bin/env python3
"""Import one large, manually supplied Sarasota property snapshot as one audited import.

This command is deliberately file-based. It is for an operator who already has an approved
manual snapshot and must not be used to enable or schedule live property collection. The normal
HTTP importer remains bounded for ordinary uploads; this path streams a generated normalized CSV
in parser-sized chunks so one county snapshot keeps one property_import_id and one current view.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))

from app.audit import record_audit  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Parcel,
    ParcelAddressAlias,
    PropertyBuilding,
    PropertyFieldValue,
    PropertyImport,
    PropertyImportError,
    PropertySourceRow,
    Provider,
    User,
)
from app.properties.address import normalize_address  # noqa: E402
from app.properties.importers import (  # noqa: E402
    FIELD_ALIASES,
    PROPERTY_PARSER_VERSION,
    PROPERTY_SCHEMA_VERSION,
    PROPERTY_TRANSFORMATION_VERSION,
    PropertyParseIssue,
    iter_normalized_csv_file,
)
from sqlalchemy import delete, insert, select  # noqa: E402

_BATCH_SIZE = 1000
_MATERIALIZED_DETAIL_FIELDS = (
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
    "bedrooms",
    "rooms",
    "outbuilding_count",
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_geometry(value: Any) -> Optional[dict[str, Any]]:
    if not value:
        return None
    try:
        geometry = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise ValueError("normalized CSV contains invalid geometry JSON") from exc
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("normalized CSV contains an unsupported geometry object")
    return geometry


def _flush(db, model: Any, rows: list[dict[str, Any]]) -> None:
    if rows:
        db.execute(insert(model), rows)
        rows.clear()


def import_snapshot(
    path: Path,
    *,
    provider_id: str,
    source_version: str,
    idempotency_key: str,
    authorized_snapshot: bool,
    effective_at: Optional[datetime],
    request_id: str,
) -> dict[str, Any]:
    settings = get_settings()
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".csv":
        raise ValueError("the large manual import command accepts a normalized CSV only")
    if not authorized_snapshot:
        raise PermissionError("an explicit manual snapshot attestation is required")
    content_hash = _sha256(path)
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != content_hash:
        raise ValueError("source CSV changed while it was being read")

    with SessionLocal() as db:
        provider = db.scalar(select(Provider).where(Provider.id == provider_id).with_for_update())
        if provider is None or provider.data_type != "property_bulk_file":
            raise ValueError("property provider is missing or is not a bulk-file provider")
        if provider_id == "sarasota.property_appraiser" and not authorized_snapshot:
            raise PermissionError("official Sarasota property imports require manual attestation")
        user = db.scalar(select(User).where(User.email == settings.bootstrap_admin_email))
        if user is None:
            raise ValueError("bootstrap operator user was not found")

        scoped_key = f"{provider_id}:{idempotency_key}"
        existing = db.scalar(
            select(PropertyImport).where(
                PropertyImport.provider_id == provider_id,
                PropertyImport.idempotency_key == scoped_key,
            )
        )
        if existing is not None:
            if existing.content_hash != content_hash:
                raise ValueError("idempotency key was already used for another snapshot")
            return {
                "property_import_id": existing.id,
                "content_hash": existing.content_hash,
                "status": existing.status,
                "replayed": True,
                "normalized_row_count": existing.normalized_row_count,
                "rejected_row_count": existing.rejected_row_count,
            }
        existing_hash = db.scalar(
            select(PropertyImport).where(
                PropertyImport.provider_id == provider_id,
                PropertyImport.content_hash == content_hash,
            )
        )
        if existing_hash is not None:
            return {
                "property_import_id": existing_hash.id,
                "content_hash": existing_hash.content_hash,
                "status": existing_hash.status,
                "replayed": True,
                "normalized_row_count": existing_hash.normalized_row_count,
                "rejected_row_count": existing_hash.rejected_row_count,
            }

        existing_parcel = db.scalar(
            select(Parcel.id).where(Parcel.provider_id == provider_id).limit(1)
        )
        if existing_parcel is not None:
            raise ValueError(
                "large manual import requires an empty property provider; use the bounded API "
                "importer for an incremental or replacement import"
            )
        previous = db.scalar(
            select(PropertyImport)
            .where(PropertyImport.provider_id == provider_id, PropertyImport.is_current.is_(True))
            .order_by(PropertyImport.created_at.desc())
        )
        raw_reference = _store_payload(settings, provider_id, content_hash, payload)
        now = datetime.now(timezone.utc)
        import_id = str(uuid4())
        import_record = PropertyImport(
            id=import_id,
            provider_id=provider_id,
            previous_import_id=previous.id if previous else None,
            status="parsing",
            import_mode="full",
            source_filename=path.name,
            idempotency_key=scoped_key,
            content_hash=content_hash,
            content_type="text/csv",
            source_version=source_version,
            parser_version=PROPERTY_PARSER_VERSION,
            schema_version=PROPERTY_SCHEMA_VERSION,
            acquisition_mode="manual_snapshot",
            authorization_basis="manual_attestation",
            effective_at=effective_at,
            retrieved_at=now,
            raw_payload_reference=raw_reference,
            byte_size=len(payload),
            created_by=user.id,
        )
        db.add(import_record)
        db.flush()

        # A full import rebuilds these current projections. The immutable source rows and raw
        # snapshot remain available for rollback and provenance.
        db.execute(
            delete(ParcelAddressAlias).where(
                ParcelAddressAlias.parcel_id.in_(
                    select(Parcel.id).where(Parcel.provider_id == provider_id)
                )
            )
        )
        db.execute(
            delete(PropertyBuilding).where(
                PropertyBuilding.parcel_id.in_(
                    select(Parcel.id).where(Parcel.provider_id == provider_id)
                )
            )
        )

        source_rows: list[dict[str, Any]] = []
        parcels: list[dict[str, Any]] = []
        aliases: list[dict[str, Any]] = []
        buildings: list[dict[str, Any]] = []
        field_values: list[dict[str, Any]] = []
        import_errors: list[dict[str, Any]] = []
        seen_parcels: set[str] = set()
        issue_rows: set[int] = set()
        issue_codes: dict[str, int] = {}
        normalized_count = 0
        geometry_count = 0
        row_count = 0
        source_hashes: set[tuple[str, str]] = set()
        geometry_sources: set[tuple[str, str]] = set()

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = next(csv.reader(handle), [])
        mapping = {field: field for field in FIELD_ALIASES if field in headers}
        for parsed in iter_normalized_csv_file(path, mapping=mapping, chunk_rows=_BATCH_SIZE):
            for issue in parsed.issues:
                _add_issue(import_errors, issue, import_id)
                issue_codes[issue.code] = issue_codes.get(issue.code, 0) + 1
                if issue.severity != "warning" and issue.row_number is not None:
                    issue_rows.add(issue.row_number)
            for row in parsed.rows:
                row_count += 1
                parcel_id = str(row.fields["parcel_id"])
                if parcel_id in seen_parcels:
                    issue = PropertyParseIssue(
                        "duplicate_parcel_id",
                        f"parcel ID {parcel_id} appears more than once in the import",
                        row.row_number,
                        _json(row.raw),
                    )
                    _add_issue(import_errors, issue, import_id)
                    issue_rows.add(row.row_number)
                    issue_codes[issue.code] = issue_codes.get(issue.code, 0) + 1
                    continue
                seen_parcels.add(parcel_id)
                fields = row.fields
                source_hashes.add(
                    (
                        str(fields.get("source_parcel_sales_sha256") or ""),
                        str(fields.get("source_detailed_sha256") or ""),
                    )
                )
                geometry_sources.add(
                    (
                        str(fields.get("source_geometry_service") or ""),
                        str(fields.get("source_geometry_layer") or ""),
                    )
                )
                geometry = _parse_geometry(fields.get("geometry"))
                if geometry is not None:
                    geometry_count += 1
                source_row_id = str(uuid4())
                parcel_internal_id = str(uuid4())
                raw_payload = _json({"source_file": path.name, "row": row.raw})
                source_rows.append(
                    {
                        "id": source_row_id,
                        "property_import_id": import_id,
                        "provider_id": provider_id,
                        "row_number": row.row_number,
                        "source_filename": path.name,
                        "source_parcel_id": parcel_id,
                        "row_hash": row.row_hash,
                        "raw_payload": raw_payload,
                        "normalized_fields": fields,
                        "status": "accepted",
                    }
                )
                parcel_values = {
                    "id": parcel_internal_id,
                    "provider_id": provider_id,
                    "parcel_id": parcel_id,
                    "current_import_id": import_id,
                    "current_source_row_id": source_row_id,
                    "is_active": True,
                    "source_version": source_version,
                    "effective_at": effective_at,
                    "situs_original": fields["situs_original"],
                    "normalized_address": fields["normalized_address"],
                    "address_precision": fields["address_precision"],
                    "house_number": fields.get("house_number"),
                    "street_prefix": fields.get("street_prefix"),
                    "street_name": fields.get("street_name"),
                    "street_type": fields.get("street_type"),
                    "street_suffix": fields.get("street_suffix"),
                    "unit": fields.get("unit"),
                    "municipality": fields.get("municipality"),
                    "postal_code": fields.get("postal_code"),
                    "county": fields.get("county"),
                    "latitude": fields.get("latitude"),
                    "longitude": fields.get("longitude"),
                    "geometry_json": geometry,
                    "grid": fields.get("grid"),
                    "property_use_code": fields.get("property_use_code"),
                    "property_use_category": fields.get("property_use_category"),
                    "owner_name": fields.get("owner_name"),
                    "mailing_address": fields.get("mailing_address"),
                    "year_built": fields.get("year_built"),
                    "effective_year_built": fields.get("effective_year_built"),
                    "building_area": fields.get("building_area"),
                    "living_area": fields.get("living_area"),
                    "number_of_buildings": fields.get("number_of_buildings"),
                    "number_of_units": fields.get("number_of_units"),
                    "stories": fields.get("stories"),
                    "master_parcel_id": fields.get("master_parcel_id"),
                    "data_quality": fields.get("data_quality") or {},
                }
                parcels.append(parcel_values)
                aliases.append(
                    {
                        "id": str(uuid4()),
                        "parcel_id": parcel_internal_id,
                        "property_import_id": import_id,
                        "alias_type": "source_situs",
                        "original_value": fields["situs_original"],
                        "normalized_address": fields["normalized_address"],
                    }
                )
                alternate_value = fields.get("address_alias")
                if alternate_value:
                    alternate = normalize_address(
                        alternate_value,
                        municipality=fields.get("municipality"),
                        postal_code=fields.get("postal_code"),
                    )
                    if alternate.normalized:
                        aliases.append(
                            {
                                "id": str(uuid4()),
                                "parcel_id": parcel_internal_id,
                                "property_import_id": import_id,
                                "alias_type": "source_alternate",
                                "original_value": str(alternate_value),
                                "normalized_address": alternate.normalized,
                            }
                        )
                buildings.append(
                    {
                        "id": str(uuid4()),
                        "parcel_id": parcel_internal_id,
                        "property_import_id": import_id,
                        "building_key": fields.get("master_parcel_id") or "primary",
                        "unit_count": fields.get("number_of_units"),
                        "stories": fields.get("stories"),
                        "building_area": fields.get("building_area"),
                        "footprint_json": None,
                    }
                )
                for field_name in _MATERIALIZED_DETAIL_FIELDS:
                    if not fields.get(field_name):
                        continue
                    field_values.append(
                        {
                            "id": str(uuid4()),
                            "property_import_id": import_id,
                            "parcel_id": parcel_internal_id,
                            "source_row_id": source_row_id,
                            "field_name": field_name,
                            "raw_value": row.raw.get(field_name),
                            "normalized_value": _json(fields.get(field_name)),
                            "transformation": "property_field_normalization",
                            "transformation_version": PROPERTY_TRANSFORMATION_VERSION,
                            "confidence": 1.0,
                            "available_at": effective_at or now,
                            "retrieved_at": now,
                        }
                    )
                normalized_count += 1
                if len(source_rows) >= _BATCH_SIZE:
                    _flush(db, PropertySourceRow, source_rows)
                    _flush(db, Parcel, parcels)
                    _flush(db, ParcelAddressAlias, aliases)
                    _flush(db, PropertyBuilding, buildings)
                    _flush(db, PropertyFieldValue, field_values)
                    db.flush()
        _flush(db, PropertySourceRow, source_rows)
        _flush(db, Parcel, parcels)
        _flush(db, ParcelAddressAlias, aliases)
        _flush(db, PropertyBuilding, buildings)
        _flush(db, PropertyFieldValue, field_values)
        _flush(db, PropertyImportError, import_errors)
        db.flush()

        if len(source_hashes) != 1:
            raise ValueError("source parcel/sales and detailed hashes are not consistent")
        if len(geometry_sources) != 1:
            raise ValueError("source GIS service/layer provenance is not consistent")
        if normalized_count == 0:
            raise ValueError("normalized CSV contained no accepted property rows")
        if previous is not None:
            previous.is_current = False
        import_record.is_current = True
        import_record.normalized_row_count = normalized_count
        import_record.rejected_row_count = len(issue_rows)
        import_record.status = "imported_with_rejections" if issue_rows else "imported"
        import_record.completed_at = datetime.now(timezone.utc)
        record_audit(
            db,
            action="property.imported",
            resource_type="property_import",
            resource_id=import_id,
            actor_user_id=user.id,
            request_id=request_id,
            metadata={
                "provider_id": provider_id,
                "source_version": source_version,
                "import_mode": "full",
                "acquisition_mode": "manual_snapshot",
                "authorization_basis": "manual_attestation",
                "normalized_row_count": normalized_count,
                "rejected_row_count": len(issue_rows),
                "geometry_row_count": geometry_count,
                "source_hashes": sorted(source_hashes),
                "geometry_sources": sorted(geometry_sources),
                "parser_mode": "streaming_normalized_csv",
                "parser_chunk_size": _BATCH_SIZE,
            },
        )
        db.commit()
        return {
            "property_import_id": import_id,
            "provider_id": provider_id,
            "status": import_record.status,
            "source_version": source_version,
            "content_hash": content_hash,
            "normalized_row_count": normalized_count,
            "rejected_row_count": len(issue_rows),
            "row_count_seen": row_count,
            "geometry_row_count": geometry_count,
            "error_codes": issue_codes,
            "source_hashes": sorted(source_hashes),
            "geometry_sources": sorted(geometry_sources),
            "acquisition_mode": "manual_snapshot",
            "authorization_basis": "manual_attestation",
            "raw_payload_reference": raw_reference,
            "replayed": False,
        }


def _add_issue(target: list[dict[str, Any]], issue: PropertyParseIssue, import_id: str) -> None:
    target.append(
        {
            "id": str(uuid4()),
            "property_import_id": import_id,
            "row_number": issue.row_number,
            "code": issue.code,
            "message": issue.message,
            "raw_payload": issue.raw_payload,
        }
    )


def _store_payload(settings: Any, provider_id: str, content_hash: str, payload: bytes) -> str:
    from app.providers.storage import build_snapshot_store

    return build_snapshot_store(settings).put(provider_id, content_hash, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--provider-id", default="sarasota.property_appraiser")
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--effective-at", default=None)
    parser.add_argument("--request-id", default="manual-sarasota-property-import")
    parser.add_argument(
        "--authorized-snapshot",
        action="store_true",
        help="attest that this file is an operator-supplied manual snapshot",
    )
    args = parser.parse_args()
    effective_at = (
        datetime.fromisoformat(args.effective_at.replace("Z", "+00:00"))
        if args.effective_at
        else None
    )
    result = import_snapshot(
        args.csv_path.resolve(),
        provider_id=args.provider_id,
        source_version=args.source_version,
        idempotency_key=args.idempotency_key,
        authorized_snapshot=args.authorized_snapshot,
        effective_at=effective_at,
        request_id=args.request_id,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
