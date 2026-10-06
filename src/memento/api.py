from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

from .serving import PredictionStore, SignalStore, SIGNAL_ID


API_CONTRACT_VERSION = "memento-attention-api-v1"
SIGNAL_API_CONTRACT_VERSION = "memento-signal-api-v1"
WireDecimal = Annotated[
    Decimal,
    PlainSerializer(lambda value: format(value, "f"), return_type=str, when_used="json"),
]
Score = Annotated[WireDecimal, Field(ge=Decimal("0"), le=Decimal("1"))]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiError(WireModel):
    api_contract_version: Literal["memento-attention-api-v1"] = API_CONTRACT_VERSION
    code: str
    message: str


class SignalApiError(WireModel):
    api_contract_version: Literal["memento-signal-api-v1"] = SIGNAL_API_CONTRACT_VERSION
    code: str
    message: str


class HealthResponse(WireModel):
    api_contract_version: Literal["memento-attention-api-v1"] = API_CONTRACT_VERSION
    status: Literal["ok"] = "ok"
    prediction_set_id: str


class RunMetadata(WireModel):
    prediction_set_id: str
    prediction_as_of: datetime
    prediction_date: date
    candidate_count: Annotated[int, Field(ge=0)]
    display_count: Annotated[int, Field(ge=0, le=10)]
    canonical_dataset_id: str
    source_release_set_id: str
    source_release_ids: list[str]
    metric_contract_version: str
    demand_forecast_version: str
    inventory_projection_version: str
    ranker_version: str
    configuration_hash: str


class AttentionSummary(WireModel):
    eligible_candidate_count: Annotated[int, Field(ge=0)]
    displayed_prediction_count: Annotated[int, Field(ge=0, le=10)]
    estimated_lost_units: WireDecimal
    estimated_lost_sales_amount: WireDecimal


class DisplayIdentity(WireModel):
    item_name: str
    company_item_id: str
    source_product_id: str
    store_name: str
    source_location_id: str


class AttentionPrediction(WireModel):
    prediction_id: Annotated[str, Field(pattern=r"^oos_[0-9a-f]{64}$")]
    rank_position: Annotated[int, Field(ge=1, le=10)]
    store_id: str
    product_id: str
    identity: DisplayIdentity
    predicted_oos_date: date
    estimated_lost_units: WireDecimal
    estimated_lost_sales_amount: WireDecimal
    impact_score: Score
    reaction_score: Score
    prediction_confidence_score: Score
    rank_score: Score


class AttentionQueueResponse(WireModel):
    api_contract_version: Literal["memento-attention-api-v1"] = API_CONTRACT_VERSION
    run: RunMetadata
    summary: AttentionSummary
    predictions: list[AttentionPrediction]


class AttentionDetailPrediction(AttentionPrediction):
    prediction_as_of: datetime
    prediction_date: date
    company_id: str
    brand_id: str
    earliest_oos_date: date | None
    latest_oos_date: date | None
    days_until_predicted_oos: int
    minimum_reaction_days: Annotated[int, Field(ge=0)]
    action_slack_days: int
    forecast_wape: WireDecimal | None
    forecast_error_band: WireDecimal
    forecast_quality: Score
    data_completeness: Score
    oos_date_span_days: Annotated[int, Field(ge=0)] | None
    timing_stability_score: Score
    source_release_ids: list[str]
    source_release_set_id: str
    metric_contract_version: str
    demand_forecast_version: str
    inventory_projection_version: str
    ranker_version: str
    configuration_hash: str
    starting_on_hand_units: WireDecimal


class EvidenceRow(WireModel):
    prediction_id: Annotated[str, Field(pattern=r"^oos_[0-9a-f]{64}$")]
    projection_date: date
    path: Literal["low", "base", "high"]
    demand_units: WireDecimal
    scheduled_inbound_units: WireDecimal
    opening_units: WireDecimal
    available_units: WireDecimal
    fulfilled_units: WireDecimal
    lost_units: WireDecimal
    projected_ending_on_hand_units: WireDecimal


class ScheduledInbound(WireModel):
    expected_store_receipt_date: date
    scheduled_inbound_units: WireDecimal


class AttentionDetailResponse(WireModel):
    api_contract_version: Literal["memento-attention-api-v1"] = API_CONTRACT_VERSION
    prediction: AttentionDetailPrediction
    evidence: Annotated[list[EvidenceRow], Field(min_length=84, max_length=84)]
    scheduled_inbound: list[ScheduledInbound]


class SignalIdentity(DisplayIdentity):
    pass


class SignalRunMetadata(WireModel):
    signal_set_id: str
    signal_as_of: datetime
    candidate_count: Annotated[int, Field(ge=0)]
    display_count: Annotated[int, Field(ge=0, le=10)]
    candidate_counts_by_type: dict[Literal["availability", "demand_momentum", "inventory_imbalance"], Annotated[int, Field(ge=0)]]
    canonical_dataset_id: str
    source_release_set_id: str
    source_release_ids: list[str]
    metric_contract_version: str
    signal_publication_version: str
    ranker_version: str
    configuration_hash: str


class SignalRow(WireModel):
    signal_id: Annotated[str, Field(pattern=r"^sig_[0-9a-f]{64}$")]
    signal_type: Literal["availability", "demand_momentum", "inventory_imbalance"]
    signal_direction: Literal["risk", "acceleration", "deceleration", "excess"]
    observation_date: date
    store_id: str
    product_id: str
    identity: SignalIdentity
    headline_metric_name: str
    headline_metric_value: WireDecimal
    estimated_retail_sales_impact_amount: WireDecimal | None
    estimated_contribution_impact_amount: WireDecimal | None
    estimated_cost_impact_amount: WireDecimal | None
    inventory_cost_exposed_amount: WireDecimal | None
    carrying_cost_28d_amount: WireDecimal | None
    economic_impact_basis: str
    days_until_material_impact: Annotated[int, Field(ge=1, le=28)]
    minimum_reaction_days: Annotated[int, Field(ge=0)]
    action_slack_days: int
    impact_score: Score
    reaction_score: Score
    confidence_score: Score
    rank_score: Score
    overall_rank_position: Annotated[int, Field(ge=1)]
    signal_type_rank_position: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def validate_type_specific_contract(self) -> "SignalRow":
        expected_direction = {"availability": {"risk"}, "demand_momentum": {"acceleration", "deceleration"}, "inventory_imbalance": {"excess"}}
        if self.signal_direction not in expected_direction[self.signal_type]:
            raise ValueError("signal direction does not match signal type")
        inventory_values = (self.estimated_cost_impact_amount, self.inventory_cost_exposed_amount, self.carrying_cost_28d_amount)
        if self.signal_type == "inventory_imbalance":
            if self.estimated_retail_sales_impact_amount is not None or self.estimated_contribution_impact_amount is not None or any(value is None for value in inventory_values):
                raise ValueError("inventory imbalance economics do not match contract")
        elif self.estimated_retail_sales_impact_amount is None or self.estimated_contribution_impact_amount is None or any(value is not None for value in inventory_values):
            raise ValueError("sales signal economics do not match contract")
        return self


class SignalQueueResponse(WireModel):
    api_contract_version: Literal["memento-signal-api-v1"] = SIGNAL_API_CONTRACT_VERSION
    run: SignalRunMetadata
    signals: Annotated[list[SignalRow], Field(max_length=10)]


class SignalEvidenceRow(WireModel):
    signal_id: Annotated[str, Field(pattern=r"^sig_[0-9a-f]{64}$")]
    evidence_type: Literal["historical_week", "forward_demand", "inventory_projection"]
    evidence_date: date
    path: Literal["low", "base", "high"] | None
    actual_units: WireDecimal | None
    retailer_forecast_units: WireDecimal | None
    adjusted_forecast_units: WireDecimal | None
    demand_units: WireDecimal | None
    scheduled_inbound_units: WireDecimal | None
    opening_units: WireDecimal | None
    ending_units: WireDecimal | None
    lost_units: WireDecimal | None
    target_units: WireDecimal | None


class SignalDetailRow(SignalRow):
    signal_as_of: datetime
    company_id: str
    brand_id: str
    forecast_quality: Score
    data_completeness: Score
    stability_score: Score
    source_release_ids: list[str]
    source_release_set_id: str
    canonical_dataset_id: str
    metric_contract_version: str
    signal_publication_version: str
    ranker_version: str
    configuration_hash: str


class SignalDetailResponse(WireModel):
    api_contract_version: Literal["memento-signal-api-v1"] = SIGNAL_API_CONTRACT_VERSION
    signal: SignalDetailRow
    evidence: list[SignalEvidenceRow]


class ApiProblem(Exception):
    def __init__(self, status_code: int, code: str, message: str, api_contract_version: str = API_CONTRACT_VERSION):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.api_contract_version = api_contract_version


def _error_response(status_code: int, code: str, message: str, api_contract_version: str = API_CONTRACT_VERSION) -> JSONResponse:
    payload = SignalApiError(code=code, message=message) if api_contract_version == SIGNAL_API_CONTRACT_VERSION else ApiError(code=code, message=message)
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _signal_problem(status_code: int, code: str, message: str) -> ApiProblem:
    return ApiProblem(status_code, code, message, SIGNAL_API_CONTRACT_VERSION)


def _run_metadata(manifest: dict[str, object]) -> RunMetadata:
    return RunMetadata.model_validate({name: manifest[name] for name in RunMetadata.model_fields})


def _queue_prediction(row: dict[str, object], identity: dict[str, str]) -> AttentionPrediction:
    payload = {name: row[name] for name in AttentionPrediction.model_fields if name != "identity"}
    return AttentionPrediction.model_validate({**payload, "identity": identity})


def _load_queue(store: PredictionStore) -> tuple[dict[str, object], list[dict[str, object]], dict[str, dict[str, str]]]:
    manifest = store.run()
    predictions = store.top_predictions()
    identities = store.display_identities(predictions) if predictions else {}
    return manifest, predictions, identities


def _validate_queue_release(
    manifest: dict[str, object], predictions: list[dict[str, object]]
) -> None:
    display_count = int(manifest["display_count"])
    candidate_count = int(manifest["candidate_count"])
    ranks = [int(row["rank_position"]) for row in predictions]
    identities = [str(row["prediction_id"]) for row in predictions]
    if display_count != len(predictions) or candidate_count < display_count:
        raise ValueError("prediction display count mismatch")
    if ranks != list(range(1, len(predictions) + 1)):
        raise ValueError("prediction ranks must be unique and contiguous")
    if len(identities) != len(set(identities)):
        raise ValueError("prediction identities must be unique")


def _validate_signal_queue_release(
    manifest: dict[str, object], signals: list[dict[str, object]], signal_type: str | None,
) -> None:
    candidate_count = int(manifest["candidate_count"])
    display_count = int(manifest["display_count"])
    counts = manifest["candidate_counts_by_type"]
    if not isinstance(counts, dict) or sum(int(value) for value in counts.values()) != candidate_count:
        raise ValueError("signal candidate counts do not reconcile")
    if display_count != min(candidate_count, 10):
        raise ValueError("signal display count does not reconcile")
    identities = [str(row["signal_id"]) for row in signals]
    overall_ranks = [int(row["overall_rank_position"]) for row in signals]
    if len(identities) != len(set(identities)) or overall_ranks != sorted(set(overall_ranks)):
        raise ValueError("signal identities and overall ranks must be unique and ordered")
    if signal_type is None:
        if len(signals) != display_count or overall_ranks != list(range(1, display_count + 1)):
            raise ValueError("overall signal queue must retain contiguous published ranks")
    elif any(row["signal_type"] != signal_type for row in signals):
        raise ValueError("filtered signal queue contains another signal type")


def _validated_evidence(
    prediction: dict[str, object], evidence: list[EvidenceRow]
) -> dict[str, list[EvidenceRow]]:
    prediction_id = str(prediction["prediction_id"])
    prediction_date = prediction["prediction_date"]
    if not isinstance(prediction_date, date):
        raise ValueError("prediction date is invalid")
    expected_dates = {
        prediction_date + timedelta(days=offset) for offset in range(1, 29)
    }
    paths: dict[str, list[EvidenceRow]] = {}
    for path in ("low", "base", "high"):
        rows = sorted(
            (row for row in evidence if row.path == path),
            key=lambda row: row.projection_date,
        )
        dates = {row.projection_date for row in rows}
        if (
            len(rows) != 28
            or dates != expected_dates
            or any(row.prediction_id != prediction_id for row in rows)
        ):
            raise ValueError("prediction evidence must contain three complete 28-day paths")
        paths[path] = rows
    if len(evidence) != 84:
        raise ValueError("prediction evidence must contain three complete 28-day paths")
    return paths


def _validated_signal_evidence(signal: SignalDetailRow, evidence: list[SignalEvidenceRow]) -> None:
    if any(row.signal_id != signal.signal_id for row in evidence):
        raise ValueError("signal evidence identity mismatch")
    if signal.signal_type in {"availability", "inventory_imbalance"}:
        expected_dates = {signal.observation_date + timedelta(days=offset) for offset in range(1, 29)}
        if len(evidence) != 84 or any(row.evidence_type != "inventory_projection" for row in evidence):
            raise ValueError("inventory signal evidence must contain three complete 28-day paths")
        for path in ("low", "base", "high"):
            rows = [row for row in evidence if row.path == path]
            if len(rows) != 28 or {row.evidence_date for row in rows} != expected_dates:
                raise ValueError("inventory signal evidence must contain three complete 28-day paths")
        if any(
            row.demand_units is None or row.scheduled_inbound_units is None or row.opening_units is None
            or row.ending_units is None or row.lost_units is None
            or row.actual_units is not None or row.retailer_forecast_units is not None or row.adjusted_forecast_units is not None
            for row in evidence
        ):
            raise ValueError("inventory signal evidence fields do not match contract")
        if signal.signal_type == "availability" and any(row.target_units is not None for row in evidence):
            raise ValueError("availability evidence cannot contain an inventory target")
        if signal.signal_type == "inventory_imbalance" and any(row.target_units is None for row in evidence):
            raise ValueError("inventory imbalance evidence requires an inventory target")
        return
    historical = [row for row in evidence if row.evidence_type == "historical_week"]
    forward = [row for row in evidence if row.evidence_type == "forward_demand"]
    expected_forward = {signal.observation_date + timedelta(days=offset) for offset in range(1, 29)}
    if (
        len(evidence) != 36 or len(historical) != 8 or len(forward) != 28
        or len({row.evidence_date for row in historical}) != 8
        or any(row.path is not None or row.evidence_date >= signal.observation_date for row in historical)
        or any(row.path != "base" for row in forward)
        or {row.evidence_date for row in forward} != expected_forward
        or any(
            row.actual_units is None or row.retailer_forecast_units is None
            or row.adjusted_forecast_units is not None or row.demand_units is not None
            or row.scheduled_inbound_units is not None or row.opening_units is not None
            or row.ending_units is not None or row.lost_units is not None or row.target_units is not None
            for row in historical
        )
        or any(
            row.retailer_forecast_units is None or row.adjusted_forecast_units is None
            or row.actual_units is not None or row.demand_units is not None
            or row.scheduled_inbound_units is not None or row.opening_units is not None
            or row.ending_units is not None or row.lost_units is not None or row.target_units is not None
            for row in forward
        )
    ):
        raise ValueError("demand momentum evidence must contain eight historical weeks and 28 forward days")


def create_app(data_root: Path) -> FastAPI:
    root = data_root.resolve()
    app = FastAPI(title="Memento Attention API", version=API_CONTRACT_VERSION)

    def prediction_store() -> PredictionStore:
        return PredictionStore(root / "predictions", root / "canonical")

    def signal_store() -> SignalStore:
        return SignalStore(root / "signals", root / "canonical")

    @app.exception_handler(ApiProblem)
    async def api_problem_handler(_request: Request, exc: ApiProblem) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.api_contract_version)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(request: Request, _exc: RequestValidationError) -> JSONResponse:
        version = SIGNAL_API_CONTRACT_VERSION if request.url.path.startswith("/v1/signals") else API_CONTRACT_VERSION
        return _error_response(422, "invalid_request", "The request does not match the API contract.", version)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, _exc: Exception) -> JSONResponse:
        if request.url.path.startswith("/v1/signals"):
            return _error_response(500, "internal_error", "The Memento Signal API could not complete the request.", SIGNAL_API_CONTRACT_VERSION)
        return _error_response(500, "internal_error", "The Attention API could not complete the request.")

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        try:
            manifest = prediction_store().run()
            return HealthResponse(prediction_set_id=str(manifest["prediction_set_id"]))
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError) as exc:
            raise ApiProblem(503, "release_unavailable", "The current prediction release is unavailable or invalid.") from exc

    @app.get(
        "/v1/attention",
        response_model=AttentionQueueResponse,
        responses={503: {"model": ApiError}},
    )
    def attention_queue() -> AttentionQueueResponse:
        try:
            manifest, predictions, identities = _load_queue(prediction_store())
            _validate_queue_release(manifest, predictions)
            queue = [_queue_prediction(row, identities[str(row["prediction_id"])]) for row in predictions]
            lost_units = sum((Decimal(str(row["estimated_lost_units"])) for row in predictions), Decimal("0"))
            lost_sales = sum((Decimal(str(row["estimated_lost_sales_amount"])) for row in predictions), Decimal("0"))
            return AttentionQueueResponse(
                run=_run_metadata(manifest),
                summary=AttentionSummary(
                    eligible_candidate_count=int(manifest["candidate_count"]),
                    displayed_prediction_count=len(queue),
                    estimated_lost_units=lost_units,
                    estimated_lost_sales_amount=lost_sales,
                ),
                predictions=queue,
            )
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError) as exc:
            raise ApiProblem(503, "release_integrity_error", "The Attention release failed integrity validation.") from exc

    @app.get(
        "/v1/attention/{prediction_id}",
        response_model=AttentionDetailResponse,
        responses={404: {"model": ApiError}, 422: {"model": ApiError}, 503: {"model": ApiError}},
    )
    def attention_detail(prediction_id: str) -> AttentionDetailResponse:
        try:
            store = prediction_store()
            prediction = store.prediction(prediction_id)
            if prediction is None:
                raise ApiProblem(404, "prediction_not_found", "The prediction is not in the current Attention queue.")
            identity = store.display_identity(prediction)
            raw_evidence = store.evidence(prediction_id)
            evidence = [EvidenceRow.model_validate(row) for row in raw_evidence]
            base_rows = _validated_evidence(prediction, evidence)["base"]
            schedule = [
                ScheduledInbound(
                    expected_store_receipt_date=row.projection_date,
                    scheduled_inbound_units=row.scheduled_inbound_units,
                )
                for row in base_rows
                if row.scheduled_inbound_units > 0
            ]
            payload = {
                name: prediction[name]
                for name in AttentionDetailPrediction.model_fields
                if name not in {"identity", "starting_on_hand_units"}
            }
            detail = AttentionDetailPrediction.model_validate({
                **payload,
                "identity": identity,
                "starting_on_hand_units": base_rows[0].opening_units,
            })
            return AttentionDetailResponse(prediction=detail, evidence=evidence, scheduled_inbound=schedule)
        except ApiProblem:
            raise
        except ValueError as exc:
            if "prediction identity" in str(exc):
                raise ApiProblem(422, "invalid_prediction_id", "The prediction identifier is invalid.") from exc
            raise ApiProblem(503, "release_integrity_error", "The Attention release failed integrity validation.") from exc
        except (FileNotFoundError, OSError, KeyError, TypeError) as exc:
            raise ApiProblem(503, "release_integrity_error", "The Attention release failed integrity validation.") from exc

    @app.get("/v1/signals", response_model=SignalQueueResponse, responses={503: {"model": SignalApiError}})
    def signal_queue(signal_type: Literal["availability", "demand_momentum", "inventory_imbalance"] | None = None) -> SignalQueueResponse:
        try:
            store = signal_store()
            manifest = store.run()
            rows = store.top_signals(signal_type)
            _validate_signal_queue_release(manifest, rows, signal_type)
            identities = store.display_identities(rows) if rows else {}
            signals = []
            for row in rows:
                payload = {name: row[name] for name in SignalRow.model_fields if name != "identity"}
                signals.append(SignalRow.model_validate({**payload, "identity": identities[str(row["signal_id"])]}))
            run = SignalRunMetadata.model_validate({name: manifest[name] for name in SignalRunMetadata.model_fields})
            return SignalQueueResponse(run=run, signals=signals)
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError) as exc:
            raise _signal_problem(503, "release_integrity_error", "The Memento Signal release failed integrity validation.") from exc

    @app.get("/v1/signals/{signal_id}", response_model=SignalDetailResponse, responses={404: {"model": SignalApiError}, 422: {"model": SignalApiError}, 503: {"model": SignalApiError}})
    def signal_detail(signal_id: str) -> SignalDetailResponse:
        if not SIGNAL_ID.fullmatch(signal_id):
            raise _signal_problem(422, "invalid_signal_id", "The signal identifier is invalid.")
        try:
            store = signal_store()
            row = store.signal(signal_id)
            if row is None:
                raise _signal_problem(404, "signal_not_found", "The signal is not in the current overall top ten.")
            identity = store.display_identities([row])[signal_id]
            payload = {name: row[name] for name in SignalDetailRow.model_fields if name != "identity"}
            detail = SignalDetailRow.model_validate({**payload, "identity": identity})
            evidence = [SignalEvidenceRow.model_validate(item) for item in store.evidence(signal_id)]
            _validated_signal_evidence(detail, evidence)
            return SignalDetailResponse(signal=detail, evidence=evidence)
        except ApiProblem:
            raise
        except ValueError as exc:
            if "signal identity" in str(exc):
                raise _signal_problem(422, "invalid_signal_id", "The signal identifier is invalid.") from exc
            raise _signal_problem(503, "release_integrity_error", "The Memento Signal release failed integrity validation.") from exc
        except (FileNotFoundError, OSError, KeyError, TypeError) as exc:
            raise _signal_problem(503, "release_integrity_error", "The Memento Signal release failed integrity validation.") from exc

    return app


app = create_app(Path(os.environ.get("MEMENTO_DATA_ROOT", "data")))
