"""add property imports, parcels, provenance, and incident matching"""

import sqlalchemy as sa
from alembic import op

revision = "0007_property_resolution"
down_revision = "0006_scope_incident_aliases_by_provider"
branch_labels = None
depends_on = None


def _json() -> sa.JSON:
    return sa.JSON()


def upgrade() -> None:
    with op.batch_alter_table("dispatch_observations", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("location_precision", sa.String(40), nullable=True))
        batch_op.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Float(), nullable=True))

    op.create_table(
        "property_mapping_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("mapping", _json(), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "provider_id", "name", name="uq_property_mapping_profile_provider_name"
        ),
    )
    op.create_index(
        "ix_property_mapping_profiles_provider_id", "property_mapping_profiles", ["provider_id"]
    )

    op.create_table(
        "property_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column(
            "mapping_profile_id",
            sa.String(36),
            sa.ForeignKey("property_mapping_profiles.id"),
            nullable=True,
        ),
        sa.Column(
            "previous_import_id", sa.String(36), sa.ForeignKey("property_imports.id"), nullable=True
        ),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("import_mode", sa.String(24), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(320), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("source_version", sa.String(120), nullable=False),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("acquisition_mode", sa.String(32), nullable=False),
        sa.Column("authorization_basis", sa.String(120), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload_reference", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("normalized_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("removed_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint(
            "provider_id", "idempotency_key", name="uq_property_import_provider_key"
        ),
        sa.UniqueConstraint("provider_id", "content_hash", name="uq_property_import_provider_hash"),
    )
    op.create_index("ix_property_imports_provider_id", "property_imports", ["provider_id"])
    op.create_index("ix_property_imports_content_hash", "property_imports", ["content_hash"])
    op.create_index("ix_property_imports_is_current", "property_imports", ["is_current"])

    op.create_table(
        "property_import_errors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "property_import_id",
            sa.String(36),
            sa.ForeignKey("property_imports.id"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_property_import_errors_property_import_id",
        "property_import_errors",
        ["property_import_id"],
    )

    op.create_table(
        "property_source_rows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "property_import_id",
            sa.String(36),
            sa.ForeignKey("property_imports.id"),
            nullable=False,
        ),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("source_parcel_id", sa.String(160), nullable=True),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("normalized_fields", _json(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "property_import_id", "row_number", name="uq_property_source_import_row"
        ),
    )
    op.create_index(
        "ix_property_source_rows_property_import_id", "property_source_rows", ["property_import_id"]
    )
    op.create_index("ix_property_source_rows_provider_id", "property_source_rows", ["provider_id"])
    op.create_index(
        "ix_property_source_rows_source_parcel_id", "property_source_rows", ["source_parcel_id"]
    )

    op.create_table(
        "parcels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("parcel_id", sa.String(160), nullable=False),
        sa.Column(
            "current_import_id", sa.String(36), sa.ForeignKey("property_imports.id"), nullable=True
        ),
        sa.Column(
            "current_source_row_id",
            sa.String(36),
            sa.ForeignKey("property_source_rows.id"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_version", sa.String(120), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("situs_original", sa.Text(), nullable=False),
        sa.Column("normalized_address", sa.Text(), nullable=False),
        sa.Column("address_precision", sa.String(40), nullable=False),
        sa.Column("house_number", sa.String(40), nullable=True),
        sa.Column("street_prefix", sa.String(16), nullable=True),
        sa.Column("street_name", sa.String(120), nullable=True),
        sa.Column("street_type", sa.String(32), nullable=True),
        sa.Column("street_suffix", sa.String(16), nullable=True),
        sa.Column("unit", sa.String(40), nullable=True),
        sa.Column("municipality", sa.String(120), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("county", sa.String(120), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("geometry_json", _json(), nullable=True),
        sa.Column("grid", sa.String(50), nullable=True),
        sa.Column("property_use_code", sa.String(80), nullable=True),
        sa.Column("property_use_category", sa.String(120), nullable=True),
        sa.Column("owner_name", sa.Text(), nullable=True),
        sa.Column("mailing_address", sa.Text(), nullable=True),
        sa.Column("year_built", sa.Integer(), nullable=True),
        sa.Column("effective_year_built", sa.Integer(), nullable=True),
        sa.Column("building_area", sa.Float(), nullable=True),
        sa.Column("living_area", sa.Float(), nullable=True),
        sa.Column("number_of_buildings", sa.Integer(), nullable=True),
        sa.Column("number_of_units", sa.Integer(), nullable=True),
        sa.Column("stories", sa.Integer(), nullable=True),
        sa.Column("master_parcel_id", sa.String(160), nullable=True),
        sa.Column("data_quality", _json(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("provider_id", "parcel_id", name="uq_parcel_provider_parcel_id"),
    )
    op.create_index("ix_parcels_provider_id", "parcels", ["provider_id"])
    op.create_index("ix_parcels_is_active", "parcels", ["is_active"])
    op.create_index("ix_parcels_address_search", "parcels", ["provider_id", "normalized_address"])
    op.create_index(
        "ix_parcels_street_search", "parcels", ["provider_id", "street_name", "house_number"]
    )
    op.create_index(
        "ix_parcels_municipality_zip", "parcels", ["provider_id", "municipality", "postal_code"]
    )

    op.create_table(
        "parcel_address_aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("parcel_id", sa.String(36), sa.ForeignKey("parcels.id"), nullable=False),
        sa.Column(
            "property_import_id",
            sa.String(36),
            sa.ForeignKey("property_imports.id"),
            nullable=False,
        ),
        sa.Column("alias_type", sa.String(40), nullable=False),
        sa.Column("original_value", sa.Text(), nullable=False),
        sa.Column("normalized_address", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "parcel_id", "normalized_address", "alias_type", name="uq_parcel_address_alias"
        ),
    )
    op.create_index("ix_parcel_address_aliases_parcel_id", "parcel_address_aliases", ["parcel_id"])
    op.create_index(
        "ix_parcel_address_aliases_property_import_id",
        "parcel_address_aliases",
        ["property_import_id"],
    )

    op.create_table(
        "property_buildings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("parcel_id", sa.String(36), sa.ForeignKey("parcels.id"), nullable=False),
        sa.Column(
            "property_import_id",
            sa.String(36),
            sa.ForeignKey("property_imports.id"),
            nullable=False,
        ),
        sa.Column("building_key", sa.String(120), nullable=False),
        sa.Column("unit_count", sa.Integer(), nullable=True),
        sa.Column("stories", sa.Integer(), nullable=True),
        sa.Column("building_area", sa.Float(), nullable=True),
        sa.Column("footprint_json", _json(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("parcel_id", "building_key", name="uq_property_building_parcel_key"),
    )
    op.create_index("ix_property_buildings_parcel_id", "property_buildings", ["parcel_id"])
    op.create_index(
        "ix_property_buildings_property_import_id", "property_buildings", ["property_import_id"]
    )

    op.create_table(
        "property_field_values",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "property_import_id",
            sa.String(36),
            sa.ForeignKey("property_imports.id"),
            nullable=False,
        ),
        sa.Column("parcel_id", sa.String(36), sa.ForeignKey("parcels.id"), nullable=False),
        sa.Column(
            "source_row_id", sa.String(36), sa.ForeignKey("property_source_rows.id"), nullable=False
        ),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("transformation", sa.String(120), nullable=False),
        sa.Column("transformation_version", sa.String(80), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "property_import_id", "parcel_id", "field_name", name="uq_property_field_import_parcel"
        ),
    )
    op.create_index(
        "ix_property_field_values_property_import_id",
        "property_field_values",
        ["property_import_id"],
    )
    op.create_index("ix_property_field_values_parcel_id", "property_field_values", ["parcel_id"])
    op.create_table(
        "incident_property_match_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column(
            "property_provider_id", sa.String(100), sa.ForeignKey("providers.id"), nullable=False
        ),
        sa.Column(
            "property_import_id", sa.String(36), sa.ForeignKey("property_imports.id"), nullable=True
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("matcher_version", sa.String(80), nullable=False),
        sa.Column("address_normalization_version", sa.String(80), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("abstention_reason", sa.Text(), nullable=True),
        sa.Column("source_observation_ids", _json(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_incident_property_match_runs_incident_id",
        "incident_property_match_runs",
        ["incident_id"],
    )
    op.create_index(
        "ix_incident_property_match_runs_property_provider_id",
        "incident_property_match_runs",
        ["property_provider_id"],
    )
    op.create_index(
        "ix_incident_property_match_runs_property_import_id",
        "incident_property_match_runs",
        ["property_import_id"],
    )

    op.create_table(
        "incident_property_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "match_run_id",
            sa.String(36),
            sa.ForeignKey("incident_property_match_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column("parcel_id", sa.String(36), sa.ForeignKey("parcels.id"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("score_margin", sa.Float(), nullable=True),
        sa.Column("classification", sa.String(24), nullable=False),
        sa.Column("recommendation_status", sa.String(24), nullable=False),
        sa.Column("is_abstained", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supporting_evidence", _json(), nullable=False),
        sa.Column("contradictory_evidence", _json(), nullable=False),
        sa.Column("features", _json(), nullable=False),
        sa.Column("explanation", _json(), nullable=False),
        sa.Column("property_data_quality", _json(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("match_run_id", "parcel_id", name="uq_property_candidate_run_parcel"),
    )
    op.create_index(
        "ix_incident_property_candidates_match_run_id",
        "incident_property_candidates",
        ["match_run_id"],
    )
    op.create_index(
        "ix_incident_property_candidates_incident_id",
        "incident_property_candidates",
        ["incident_id"],
    )
    op.create_index(
        "ix_incident_property_candidates_parcel_id", "incident_property_candidates", ["parcel_id"]
    )

    op.create_table(
        "property_match_features",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("incident_property_candidates.id"),
            nullable=False,
        ),
        sa.Column("feature_name", sa.String(100), nullable=False),
        sa.Column("numeric_value", sa.Float(), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("contribution", sa.Float(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feature_version", sa.String(80), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("candidate_id", "feature_name", name="uq_property_match_feature_name"),
    )
    op.create_index(
        "ix_property_match_features_candidate_id", "property_match_features", ["candidate_id"]
    )

    op.create_table(
        "property_match_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("canonical_incidents.id"), nullable=False
        ),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("incident_property_candidates.id"),
            nullable=True,
        ),
        sa.Column("parcel_id", sa.String(36), sa.ForeignKey("parcels.id"), nullable=True),
        sa.Column(
            "match_run_id",
            sa.String(36),
            sa.ForeignKey("incident_property_match_runs.id"),
            nullable=True,
        ),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("corrected_address", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_property_match_decisions_incident_id", "property_match_decisions", ["incident_id"]
    )
    op.create_index(
        "ix_property_match_decisions_parcel_id", "property_match_decisions", ["parcel_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_property_match_decisions_parcel_id", table_name="property_match_decisions")
    op.drop_index("ix_property_match_decisions_incident_id", table_name="property_match_decisions")
    op.drop_table("property_match_decisions")
    op.drop_index("ix_property_match_features_candidate_id", table_name="property_match_features")
    op.drop_table("property_match_features")
    op.drop_index(
        "ix_incident_property_candidates_parcel_id", table_name="incident_property_candidates"
    )
    op.drop_index(
        "ix_incident_property_candidates_incident_id", table_name="incident_property_candidates"
    )
    op.drop_index(
        "ix_incident_property_candidates_match_run_id", table_name="incident_property_candidates"
    )
    op.drop_table("incident_property_candidates")
    op.drop_index(
        "ix_incident_property_match_runs_property_import_id",
        table_name="incident_property_match_runs",
    )
    op.drop_index(
        "ix_incident_property_match_runs_property_provider_id",
        table_name="incident_property_match_runs",
    )
    op.drop_index(
        "ix_incident_property_match_runs_incident_id", table_name="incident_property_match_runs"
    )
    op.drop_table("incident_property_match_runs")
    op.drop_index("ix_property_field_values_parcel_id", table_name="property_field_values")
    op.drop_index("ix_property_field_values_property_import_id", table_name="property_field_values")
    op.drop_table("property_field_values")
    op.drop_index("ix_property_buildings_property_import_id", table_name="property_buildings")
    op.drop_index("ix_property_buildings_parcel_id", table_name="property_buildings")
    op.drop_table("property_buildings")
    op.drop_index(
        "ix_parcel_address_aliases_property_import_id", table_name="parcel_address_aliases"
    )
    op.drop_index("ix_parcel_address_aliases_parcel_id", table_name="parcel_address_aliases")
    op.drop_table("parcel_address_aliases")
    for name in [
        "ix_parcels_municipality_zip",
        "ix_parcels_street_search",
        "ix_parcels_address_search",
        "ix_parcels_is_active",
        "ix_parcels_provider_id",
    ]:
        op.drop_index(name, table_name="parcels")
    op.drop_table("parcels")
    for name in [
        "ix_property_source_rows_source_parcel_id",
        "ix_property_source_rows_provider_id",
        "ix_property_source_rows_property_import_id",
    ]:
        op.drop_index(name, table_name="property_source_rows")
    op.drop_table("property_source_rows")
    op.drop_index(
        "ix_property_import_errors_property_import_id", table_name="property_import_errors"
    )
    op.drop_table("property_import_errors")
    for name in [
        "ix_property_imports_is_current",
        "ix_property_imports_content_hash",
        "ix_property_imports_provider_id",
    ]:
        op.drop_index(name, table_name="property_imports")
    op.drop_table("property_imports")
    op.drop_index(
        "ix_property_mapping_profiles_provider_id", table_name="property_mapping_profiles"
    )
    op.drop_table("property_mapping_profiles")
    with op.batch_alter_table("dispatch_observations", recreate="always") as batch_op:
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
        batch_op.drop_column("location_precision")
