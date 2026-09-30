from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from .serving import PredictionStore


API_CONTRACT_VERSION = "memento-attention-api-v1"
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


class ApiProblem(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    payload = ApiError(code=code, message=message)
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


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


def create_app(data_root: Path) -> FastAPI:
    root = data_root.resolve()
    app = FastAPI(title="Memento Attention API", version=API_CONTRACT_VERSION)

    def prediction_store() -> PredictionStore:
        return PredictionStore(root / "predictions", root / "canonical")

    @app.exception_handler(ApiProblem)
    async def api_problem_handler(_request: Request, exc: ApiProblem) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return _error_response(422, "invalid_request", "The request does not match the API contract.")

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
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
            if int(manifest["display_count"]) != len(predictions):
                raise ValueError("prediction display count mismatch")
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
            base_rows = [row for row in evidence if row.path == "base"]
            if len(base_rows) != 28 or len(evidence) != 84:
                raise ValueError("prediction evidence must contain three complete 28-day paths")
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

    return app


app = create_app(Path(os.environ.get("MEMENTO_DATA_ROOT", "data")))
