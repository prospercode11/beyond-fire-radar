from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.config import Settings
from app.models import (
    Parcel,
    ParcelAddressAlias,
    PropertyBuilding,
    PropertyFieldValue,
    PropertyImport,
    PropertyImportError,
    PropertyMappingProfile,
    PropertySourceRow,
    Provider,
)
from app.properties.address import normalize_address
from app.properties.importers import (
    PROPERTY_PARSER_VERSION,
    PROPERTY_SCHEMA_VERSION,
    PROPERTY_TRANSFORMATION_VERSION,
    NormalizedPropertyRow,
    PropertyParseIssue,
    PropertyParseResult,
    parse_property_file,
)
from app.providers.storage import build_snapshot_store


class PropertyImportConflict(ValueError):
    pass


@dataclass(frozen=True)
class PropertyImportReport:
    property_import_id: str
    provider_id: str
    status: str
    format: str
    source_version: str
    content_hash: str
    normalized_row_count: int
    rejected_row_count: int
    removed_row_count: int
    replayed: bool
    mapping: dict[str, str]
    warnings: list[str]
    errors: list[str]
    acquisition_mode: str
    authorization_basis: Optional[str]
    source_filename: Optional[str]
    parser_version: Optional[str]
    schema_version: Optional[str]
    effective_at: Optional[datetime]
    retrieved_at: Optional[datetime]
    raw_payload_reference: Optional[str]
    payload_purged_at: Optional[datetime]


def _report(
    import_record: PropertyImport,
    parsed: Optional[PropertyParseResult] = None,
    *,
    replayed: bool = False,
) -> PropertyImportReport:
    warnings: list[str] = []
    errors: list[str] = []
    mapping = {}
    if parsed is not None:
        mapping = parsed.mapping
        warnings = [issue.message for issue in parsed.issues if issue.severity == "warning"]
        errors = [issue.message for issue in parsed.issues if issue.severity != "warning"]
    return PropertyImportReport(
        property_import_id=import_record.id,
        provider_id=import_record.provider_id,
        status=import_record.status,
        format=parsed.format
        if parsed is not None
        else _format_from_filename(import_record.source_filename),
        source_version=import_record.source_version,
        content_hash=import_record.content_hash,
        normalized_row_count=import_record.normalized_row_count,
        rejected_row_count=import_record.rejected_row_count,
        removed_row_count=import_record.removed_row_count,
        replayed=replayed,
        mapping=mapping,
        warnings=warnings,
        errors=errors,
        acquisition_mode=import_record.acquisition_mode,
        authorization_basis=import_record.authorization_basis,
        source_filename=import_record.source_filename,
        parser_version=import_record.parser_version,
        schema_version=import_record.schema_version,
        effective_at=import_record.effective_at,
        retrieved_at=import_record.retrieved_at,
        raw_payload_reference=import_record.raw_payload_reference,
        payload_purged_at=import_record.payload_purged_at,
    )


def _format_from_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return {".csv": "csv", ".xlsx": "xlsx", ".zip": "zip"}.get(suffix, "unknown")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _parse_geometry(value: Any) -> Optional[dict[str, Any]]:
    if not value:
        return None
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(str(value))
        return decoded if isinstance(decoded, dict) else {"raw": str(value)}
    except json.JSONDecodeError:
        return {"raw": str(value)}


def _parcel_values(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        key: fields.get(key)
        for key in (
            "situs_original",
            "normalized_address",
            "address_precision",
            "house_number",
            "street_prefix",
            "street_name",
            "street_type",
            "street_suffix",
            "unit",
            "municipality",
            "postal_code",
            "county",
            "latitude",
            "longitude",
            "grid",
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
            "stories",
            "master_parcel_id",
        )
    }


def _apply_parcel_values(
    parcel: Parcel,
    *,
    row: PropertySourceRow,
    import_record: PropertyImport,
) -> None:
    fields = row.normalized_fields or {}
    for key, value in _parcel_values(fields).items():
        setattr(parcel, key, value)
    parcel.provider_id = import_record.provider_id
    parcel.parcel_id = str(fields["parcel_id"])
    parcel.current_import_id = import_record.id
    parcel.current_source_row_id = row.id
    parcel.is_active = True
    parcel.source_version = import_record.source_version
    parcel.effective_at = import_record.effective_at
    parcel.geometry_json = _parse_geometry(fields.get("geometry"))
    parcel.data_quality = fields.get("data_quality", {})


def _source_raw_value(row: NormalizedPropertyRow, source_header: str) -> Optional[str]:
    value = row.raw.get(source_header)
    if value is None or str(value).strip() == "":
        return None
    return str(value)


class PropertyImportService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = build_snapshot_store(settings)

    @staticmethod
    def preview(
        payload: bytes,
        *,
        content_type: Optional[str],
        filename: str,
        mapping: Optional[dict[str, str]],
    ) -> PropertyParseResult:
        return parse_property_file(payload, content_type, filename, mapping)

    def import_file(
        self,
        db: Session,
        *,
        provider_id: str,
        user_id: str,
        filename: str,
        content_type: Optional[str],
        payload: bytes,
        source_version: str,
        import_mode: str,
        effective_at: Optional[datetime],
        mapping: Optional[dict[str, str]],
        mapping_profile_id: Optional[str],
        idempotency_key: str,
        authorized_snapshot: bool,
        request_id: str,
    ) -> PropertyImportReport:
        if import_mode not in {"full", "incremental"}:
            raise ValueError("import_mode must be full or incremental")
        provider = db.scalar(select(Provider).where(Provider.id == provider_id).with_for_update())
        if provider is None:
            raise ValueError("property provider not found")
        if provider.data_type != "property_bulk_file":
            raise ValueError("provider is not a property bulk-file provider")
        if not provider_id.startswith("fixture.") and not authorized_snapshot:
            raise PermissionError(
                f"{provider.name} imports require an explicit authorized_snapshot attestation"
            )
        if provider_id == "fixture.sarasota.property_appraiser":
            acquisition_mode = "synthetic_fixture"
            authorization_basis = "fixture"
        else:
            acquisition_mode = "manual_snapshot"
            authorization_basis = "manual_attestation"
        resolved_mapping = mapping
        if mapping_profile_id:
            profile = db.get(PropertyMappingProfile, mapping_profile_id)
            if profile is None or profile.provider_id != provider_id:
                raise ValueError("mapping profile not found for provider")
            resolved_mapping = profile.mapping

        content_hash = hashlib.sha256(payload).hexdigest()
        scoped_idempotency_key = f"{provider_id}:{idempotency_key}"
        existing = db.scalar(
            select(PropertyImport).where(
                PropertyImport.provider_id == provider_id,
                PropertyImport.idempotency_key == scoped_idempotency_key,
            )
        )
        if existing is not None:
            if existing.content_hash != content_hash:
                raise PropertyImportConflict(
                    "Idempotency-Key was already used for a different property snapshot"
                )
            return _report(existing, replayed=True)
        existing_hash = db.scalar(
            select(PropertyImport).where(
                PropertyImport.provider_id == provider_id,
                PropertyImport.content_hash == content_hash,
            )
        )
        if existing_hash is not None:
            return _report(existing_hash, replayed=True)

        previous = db.scalar(
            select(PropertyImport)
            .where(PropertyImport.provider_id == provider_id, PropertyImport.is_current.is_(True))
            .order_by(PropertyImport.created_at.desc())
        )
        raw_reference = self.store.put(provider_id, content_hash, payload)
        now = datetime.now(timezone.utc)
        import_record = PropertyImport(
            id=str(uuid4()),
            provider_id=provider_id,
            mapping_profile_id=mapping_profile_id,
            previous_import_id=previous.id if previous else None,
            status="parsing",
            import_mode=import_mode,
            source_filename=filename,
            idempotency_key=scoped_idempotency_key,
            content_hash=content_hash,
            content_type=content_type or "application/octet-stream",
            source_version=source_version,
            parser_version=provider.parser_version or PROPERTY_PARSER_VERSION,
            schema_version=provider.schema_version or PROPERTY_SCHEMA_VERSION,
            acquisition_mode=acquisition_mode,
            authorization_basis=authorization_basis,
            effective_at=effective_at,
            retrieved_at=now,
            raw_payload_reference=raw_reference,
            byte_size=len(payload),
            created_by=user_id,
        )
        db.add(import_record)
        db.flush()
        parsed = parse_property_file(
            payload,
            content_type,
            filename,
            resolved_mapping,
            max_archive_members=self.settings.max_archive_members,
            max_archive_uncompressed_bytes=self.settings.max_archive_uncompressed_bytes,
        )
        seen_parcels: set[str] = set()
        accepted_rows: list[tuple[NormalizedPropertyRow, PropertySourceRow]] = []
        for row in parsed.rows:
            if row.fields["parcel_id"] in seen_parcels:
                parsed.issues.append(
                    PropertyParseIssue(
                        "duplicate_parcel_id",
                        f"parcel ID {row.fields['parcel_id']} appears more than once in the import",
                        row.row_number,
                        _json(row.raw),
                    )
                )
                continue
            seen_parcels.add(row.fields["parcel_id"])
            source_row = PropertySourceRow(
                id=str(uuid4()),
                property_import_id=import_record.id,
                provider_id=provider_id,
                row_number=row.row_number,
                source_filename=row.source_filename,
                source_parcel_id=row.fields["parcel_id"],
                row_hash=row.row_hash,
                raw_payload=_json({"source_file": row.source_filename, "row": row.raw}),
                normalized_fields=row.fields,
                status="accepted",
            )
            db.add(source_row)
            db.flush()
            accepted_rows.append((row, source_row))
        for issue in parsed.issues:
            db.add(
                PropertyImportError(
                    id=str(uuid4()),
                    property_import_id=import_record.id,
                    row_number=issue.row_number,
                    code=issue.code,
                    message=issue.message,
                    raw_payload=issue.raw_payload,
                )
            )
        if not accepted_rows:
            import_record.status = (
                "parse_failed"
                if any(issue.severity != "warning" for issue in parsed.issues)
                else "zero_row_anomaly"
            )
            import_record.error_code = next(
                (issue.code for issue in parsed.issues if issue.severity != "warning"),
                "zero_row_anomaly",
            )
            import_record.error_message = next(
                (issue.message for issue in parsed.issues if issue.severity != "warning"),
                "property import contained no usable rows",
            )
            import_record.rejected_row_count = parsed.rejected_row_count
            import_record.completed_at = datetime.now(timezone.utc)
            db.commit()
            return _report(import_record, parsed)

        if previous is not None:
            previous.is_current = False
            db.flush()
        import_record.is_current = True
        incoming_ids = {row.fields["parcel_id"] for row, _ in accepted_rows}
        removed_count = 0
        if import_mode == "full":
            # Aliases and building rows are current derived projections. The immutable source
            # rows and import payloads retain their historical values; rebuild these projections
            # from the accepted full snapshot below so superseded addresses/structures cannot
            # influence matching after replacement.
            for alias in db.scalars(
                select(ParcelAddressAlias)
                .join(Parcel, Parcel.id == ParcelAddressAlias.parcel_id)
                .where(Parcel.provider_id == provider_id)
            ).all():
                db.delete(alias)
            for building in db.scalars(
                select(PropertyBuilding)
                .join(Parcel, Parcel.id == PropertyBuilding.parcel_id)
                .where(Parcel.provider_id == provider_id)
            ).all():
                db.delete(building)
            db.flush()
            current_parcels = db.scalars(
                select(Parcel).where(Parcel.provider_id == provider_id, Parcel.is_active.is_(True))
            ).all()
            for current_parcel in current_parcels:
                if current_parcel.parcel_id not in incoming_ids:
                    current_parcel.is_active = False
                    current_parcel.current_import_id = import_record.id
                    current_parcel.data_quality = {
                        **(current_parcel.data_quality or {}),
                        "removed_by_import": import_record.id,
                    }
                    removed_count += 1
        for row, source_row in accepted_rows:
            parcel: Optional[Parcel] = db.scalar(
                select(Parcel).where(
                    Parcel.provider_id == provider_id, Parcel.parcel_id == row.fields["parcel_id"]
                )
            )
            if parcel is None:
                parcel = Parcel(
                    id=str(uuid4()),
                    provider_id=provider_id,
                    parcel_id=row.fields["parcel_id"],
                    source_version=source_version,
                    situs_original=row.fields["situs_original"],
                    normalized_address=row.fields["normalized_address"],
                    address_precision=row.fields["address_precision"],
                    data_quality={},
                )
                db.add(parcel)
                db.flush()
            _apply_parcel_values(parcel, row=source_row, import_record=import_record)
            current_alias: Optional[ParcelAddressAlias] = db.scalar(
                select(ParcelAddressAlias).where(
                    ParcelAddressAlias.parcel_id == parcel.id,
                    ParcelAddressAlias.normalized_address == row.fields["normalized_address"],
                    ParcelAddressAlias.alias_type == "source_situs",
                )
            )
            if current_alias is None:
                db.add(
                    ParcelAddressAlias(
                        id=str(uuid4()),
                        parcel_id=parcel.id,
                        property_import_id=import_record.id,
                        alias_type="source_situs",
                        original_value=row.fields["situs_original"],
                        normalized_address=row.fields["normalized_address"],
                    )
                )
            fields = row.fields
            alternate_value = fields.get("address_alias")
            if alternate_value:
                alternate = normalize_address(
                    alternate_value,
                    municipality=fields.get("municipality"),
                    postal_code=fields.get("postal_code"),
                )
                if alternate.normalized:
                    alternate_alias = db.scalar(
                        select(ParcelAddressAlias).where(
                            ParcelAddressAlias.parcel_id == parcel.id,
                            ParcelAddressAlias.normalized_address == alternate.normalized,
                            ParcelAddressAlias.alias_type == "source_alternate",
                        )
                    )
                    if alternate_alias is None:
                        db.add(
                            ParcelAddressAlias(
                                id=str(uuid4()),
                                parcel_id=parcel.id,
                                property_import_id=import_record.id,
                                alias_type="source_alternate",
                                original_value=str(alternate_value),
                                normalized_address=alternate.normalized,
                            )
                        )
            building_key = row.fields["master_parcel_id"] or "primary"
            current_building: Optional[PropertyBuilding] = db.scalar(
                select(PropertyBuilding).where(
                    PropertyBuilding.parcel_id == parcel.id,
                    PropertyBuilding.building_key == building_key,
                )
            )
            if current_building is None:
                current_building = PropertyBuilding(
                    id=str(uuid4()),
                    parcel_id=parcel.id,
                    property_import_id=import_record.id,
                    building_key=building_key,
                )
                db.add(current_building)
            current_building.property_import_id = import_record.id
            current_building.unit_count = row.fields["number_of_units"]
            current_building.stories = row.fields["stories"]
            current_building.building_area = row.fields["building_area"]
            for field_name, source_header in (resolved_mapping or {}).items():
                if field_name in {"address_alias", "geometry"}:
                    continue
                db.add(
                    PropertyFieldValue(
                        id=str(uuid4()),
                        property_import_id=import_record.id,
                        parcel_id=parcel.id,
                        source_row_id=source_row.id,
                        field_name=field_name,
                        raw_value=_source_raw_value(row, source_header),
                        normalized_value=_json(row.fields.get(field_name)),
                        transformation="property_field_normalization",
                        transformation_version=PROPERTY_TRANSFORMATION_VERSION,
                        confidence=1.0,
                        available_at=effective_at or now,
                        retrieved_at=now,
                    )
                )
        import_record.normalized_row_count = len(accepted_rows)
        import_record.rejected_row_count = parsed.rejected_row_count
        import_record.removed_row_count = removed_count
        import_record.status = (
            "imported_with_rejections"
            if any(issue.severity != "warning" for issue in parsed.issues)
            else "imported"
        )
        import_record.completed_at = datetime.now(timezone.utc)
        record_audit(
            db,
            action="property.imported",
            resource_type="property_import",
            resource_id=import_record.id,
            actor_user_id=user_id,
            request_id=request_id,
            metadata={
                "provider_id": provider_id,
                "source_version": source_version,
                "import_mode": import_mode,
                "acquisition_mode": acquisition_mode,
                "normalized_row_count": import_record.normalized_row_count,
                "rejected_row_count": import_record.rejected_row_count,
                "removed_row_count": removed_count,
            },
        )
        db.commit()
        return _report(import_record, parsed)

    def rollback(
        self, db: Session, import_record: PropertyImport, *, actor_user_id: str, request_id: str
    ) -> PropertyImportReport:
        if not import_record.is_current:
            raise ValueError("only the current property import can be rolled back")
        # Rebuild the exact projection that existed immediately before this import.  The
        # explicit import lineage is authoritative: created_at is not a safe ordering key for
        # concurrent or replayed imports, and a full snapshot must also preserve removals.
        lineage: list[PropertyImport] = []
        seen_import_ids: set[str] = set()
        prior_import_id = import_record.previous_import_id
        while prior_import_id:
            if prior_import_id in seen_import_ids:
                raise ValueError("property import lineage contains a cycle")
            seen_import_ids.add(prior_import_id)
            prior_import = db.get(PropertyImport, prior_import_id)
            if prior_import is None or prior_import.provider_id != import_record.provider_id:
                raise ValueError("property import lineage is incomplete")
            lineage.append(prior_import)
            prior_import_id = prior_import.previous_import_id
        lineage.reverse()

        latest: dict[str, tuple[PropertySourceRow, PropertyImport]] = {}
        for prior_import in lineage:
            rows = db.scalars(
                select(PropertySourceRow)
                .where(
                    PropertySourceRow.property_import_id == prior_import.id,
                    PropertySourceRow.status == "accepted",
                )
                .order_by(PropertySourceRow.row_number, PropertySourceRow.id)
            ).all()
            if prior_import.import_mode == "full":
                latest = {}
            for source_row in rows:
                if source_row.source_parcel_id:
                    latest[source_row.source_parcel_id] = (source_row, prior_import)
        parcels = db.scalars(
            select(Parcel).where(Parcel.provider_id == import_record.provider_id)
        ).all()
        restored_building_ids: set[str] = set()
        for parcel in parcels:
            previous = latest.get(parcel.parcel_id)
            if previous is None:
                parcel.is_active = False
                parcel.current_import_id = import_record.previous_import_id
                parcel.current_source_row_id = None
                parcel.data_quality = {
                    **(parcel.data_quality or {}),
                    "inactive_after_rollback": import_record.id,
                }
                continue
            source_row, prior_import = previous
            _apply_parcel_values(parcel, row=source_row, import_record=prior_import)
            fields = source_row.normalized_fields or {}
            source_aliases = [
                (
                    "source_situs",
                    fields.get("situs_original"),
                    fields.get("normalized_address"),
                )
            ]
            alternate_value = fields.get("address_alias")
            if alternate_value:
                alternate = normalize_address(
                    alternate_value,
                    municipality=fields.get("municipality"),
                    postal_code=fields.get("postal_code"),
                )
                if alternate.normalized:
                    source_aliases.append(
                        ("source_alternate", str(alternate_value), alternate.normalized)
                    )
            for alias_type, original_value, normalized_value in source_aliases:
                if not original_value or not normalized_value:
                    continue
                restored_alias = db.scalar(
                    select(ParcelAddressAlias).where(
                        ParcelAddressAlias.parcel_id == parcel.id,
                        ParcelAddressAlias.normalized_address == normalized_value,
                        ParcelAddressAlias.alias_type == alias_type,
                    )
                )
                if restored_alias is None:
                    db.add(
                        ParcelAddressAlias(
                            id=str(uuid4()),
                            parcel_id=parcel.id,
                            property_import_id=prior_import.id,
                            alias_type=alias_type,
                            original_value=str(original_value),
                            normalized_address=str(normalized_value),
                        )
                    )
            building_key = fields.get("master_parcel_id") or "primary"
            restored_building = db.scalar(
                select(PropertyBuilding).where(
                    PropertyBuilding.parcel_id == parcel.id,
                    PropertyBuilding.building_key == building_key,
                )
            )
            if restored_building is None:
                restored_building = PropertyBuilding(
                    id=str(uuid4()),
                    parcel_id=parcel.id,
                    property_import_id=prior_import.id,
                    building_key=building_key,
                )
                db.add(restored_building)
                db.flush()
            restored_building.property_import_id = prior_import.id
            restored_building.unit_count = fields.get("number_of_units")
            restored_building.stories = fields.get("stories")
            restored_building.building_area = fields.get("building_area")
            restored_building_ids.add(restored_building.id)

        # Aliases and buildings are current derived projections. Raw source rows remain
        # immutable, but rows created or retargeted by the rolled-back import must not continue
        # influencing candidate generation or claim current provenance.
        for alias in db.scalars(
            select(ParcelAddressAlias).where(
                ParcelAddressAlias.property_import_id == import_record.id
            )
        ).all():
            db.delete(alias)
        for building in db.scalars(
            select(PropertyBuilding).where(PropertyBuilding.property_import_id == import_record.id)
        ).all():
            if building.id not in restored_building_ids:
                db.delete(building)
        import_record.status = "rolled_back"
        import_record.is_current = False
        db.flush()
        if import_record.previous_import_id:
            previous_import = db.get(PropertyImport, import_record.previous_import_id)
            if previous_import is not None:
                previous_import.is_current = True
        record_audit(
            db,
            action="property.import_rolled_back",
            resource_type="property_import",
            resource_id=import_record.id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            metadata={
                "provider_id": import_record.provider_id,
                "restored_import_id": import_record.previous_import_id,
            },
        )
        db.commit()
        return _report(import_record)
