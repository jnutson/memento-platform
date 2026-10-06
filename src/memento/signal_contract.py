from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import TypedDict

import pyarrow as pa

from .metrics import confidence_score, reaction_metrics


SIGNAL_CONTRACT_VERSION = "memento-signal-metrics-v1.0.0"
SIGNAL_PUBLICATION_VERSION = "memento-signal-publication-v1"
SIGNAL_RANKER_VERSION = "memento-signal-ranker-v1"
SIGNAL_TYPE_ORDER = {"availability": 0, "demand_momentum": 1, "inventory_imbalance": 2}


class Observation(TypedDict):
    observation_date: date
    store_id: str
    product_id: str
    on_hand: float
    price: float | None
    assorted: bool
    replenishment_enabled: bool
    location_status: str
    company_item_id: str
    unit_cost: float


class ForecastVintage(TypedDict):
    target_retail_year_week: int
    memento_weekly_demand_base: Decimal
    forecast_wape: Decimal | None

SIGNAL_SCHEMA = pa.schema([
    ("signal_id", pa.string()), ("signal_type", pa.string()), ("signal_direction", pa.string()),
    ("signal_as_of", pa.timestamp("us", tz="UTC")), ("observation_date", pa.date32()),
    ("company_id", pa.string()), ("brand_id", pa.string()), ("store_id", pa.string()), ("product_id", pa.string()),
    ("headline_metric_name", pa.string()), ("headline_metric_value", pa.decimal128(20, 6)),
    ("estimated_retail_sales_impact_amount", pa.decimal128(20, 2)),
    ("estimated_contribution_impact_amount", pa.decimal128(20, 2)),
    ("estimated_cost_impact_amount", pa.decimal128(20, 2)),
    ("inventory_cost_exposed_amount", pa.decimal128(20, 2)),
    ("carrying_cost_28d_amount", pa.decimal128(20, 2)),
    ("economic_impact_basis", pa.string()), ("days_until_material_impact", pa.int32()),
    ("minimum_reaction_days", pa.int32()), ("action_slack_days", pa.int32()),
    ("forecast_quality", pa.decimal128(9, 6)), ("data_completeness", pa.decimal128(9, 6)),
    ("stability_score", pa.decimal128(9, 6)), ("impact_score", pa.decimal128(9, 6)),
    ("reaction_score", pa.decimal128(9, 6)), ("confidence_score", pa.decimal128(9, 6)),
    ("rank_score", pa.decimal128(9, 6)), ("overall_rank_position", pa.int32()),
    ("signal_type_rank_position", pa.int32()), ("is_overall_top_10", pa.bool_()),
    ("primary_economic_value", pa.decimal128(20, 2)), ("source_release_ids", pa.list_(pa.string())),
    ("source_release_set_id", pa.string()), ("canonical_dataset_id", pa.string()),
    ("metric_contract_version", pa.string()), ("signal_publication_version", pa.string()),
    ("ranker_version", pa.string()), ("configuration_hash", pa.string()),
])

EVIDENCE_SCHEMA = pa.schema([
    ("signal_id", pa.string()), ("evidence_type", pa.string()), ("evidence_date", pa.date32()),
    ("path", pa.string()), ("actual_units", pa.decimal128(20, 6)),
    ("retailer_forecast_units", pa.decimal128(20, 6)), ("adjusted_forecast_units", pa.decimal128(20, 6)),
    ("demand_units", pa.decimal128(20, 6)), ("scheduled_inbound_units", pa.decimal128(20, 6)),
    ("opening_units", pa.decimal128(20, 6)), ("ending_units", pa.decimal128(20, 6)),
    ("lost_units", pa.decimal128(20, 6)), ("target_units", pa.decimal128(20, 6)),
])


@dataclass
class CandidateBatch:
    candidates: list[dict[str, object]] = field(default_factory=list)
    evidence: list[dict[str, object]] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)

    def extend(self, other: "CandidateBatch") -> None:
        self.candidates.extend(other.candidates)
        self.evidence.extend(other.evidence)
        self.reason_codes.extend(other.reason_codes)


def decimal_value(value: float | Decimal | None, scale: int) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_EVEN)


def stable_signal_id(source_release_set_id: str, signal_as_of: str, store_id: str, product_id: str, signal_type: str, episode: str) -> str:
    preimage = "|".join((source_release_set_id, signal_as_of, store_id, product_id, signal_type, episode))
    return "sig_" + hashlib.sha256(preimage.encode()).hexdigest()


def common_signal_fields(
    observation: Observation, manifest: dict[str, object], signal_id: str,
    signal_type: str, direction: str, headline: str, value: float, days: int,
    minimum_reaction: int, quality: float, completeness: float, stability: float,
) -> dict[str, object]:
    slack, reaction = reaction_metrics(days, minimum_reaction)
    _, confidence = confidence_score(1 - quality, completeness, stability)
    return {
        "signal_id": signal_id, "signal_type": signal_type, "signal_direction": direction,
        "signal_as_of": datetime.fromisoformat(str(manifest["as_of"]).replace("Z", "+00:00")),
        "observation_date": observation["observation_date"], "company_id": "MIRO_TOYS", "brand_id": "MIRO_SPARK",
        "store_id": observation["store_id"], "product_id": observation["product_id"], "headline_metric_name": headline,
        "headline_metric_value": decimal_value(value, 6), "days_until_material_impact": days,
        "minimum_reaction_days": minimum_reaction, "action_slack_days": slack,
        "forecast_quality": decimal_value(quality, 6), "data_completeness": decimal_value(completeness, 6),
        "stability_score": decimal_value(stability, 6), "reaction_score": decimal_value(reaction, 6),
        "confidence_score": decimal_value(confidence, 6), "source_release_ids": manifest["source_release_ids"],
        "source_release_set_id": manifest["source_release_set_id"], "canonical_dataset_id": manifest["dataset_id"],
    }
