from __future__ import annotations

from collections import defaultdict

from .metrics import impact_scores, rank_score
from .signal_contract import SIGNAL_TYPE_ORDER, decimal_value


def rank_signal_candidates(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    """Assign type-relative impact and immutable overall/type ranks in place."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in candidates:
        signal_type = str(row["signal_type"])
        if signal_type not in SIGNAL_TYPE_ORDER:
            raise ValueError("unknown signal type")
        grouped[signal_type].append(row)
    for signal_type in SIGNAL_TYPE_ORDER:
        rows = grouped.get(signal_type, [])
        scores = impact_scores([float(row["primary_economic_value"]) for row in rows])
        for row, impact in zip(rows, scores, strict=True):
            row["impact_score"] = decimal_value(impact, 6)
            row["rank_score"] = decimal_value(rank_score(impact, float(row["reaction_score"]), float(row["confidence_score"])), 6)
        rows.sort(key=lambda row: (-float(row["rank_score"]), -float(row["primary_economic_value"]), int(row["days_until_material_impact"]), str(row["store_id"]), str(row["product_id"]), str(row["signal_id"])))
        for position, row in enumerate(rows, 1):
            row["signal_type_rank_position"] = position
    candidates.sort(key=lambda row: (-float(row["rank_score"]), -float(row["primary_economic_value"]), int(row["days_until_material_impact"]), SIGNAL_TYPE_ORDER[str(row["signal_type"])], str(row["store_id"]), str(row["product_id"]), str(row["signal_id"])))
    for position, row in enumerate(candidates, 1):
        row["overall_rank_position"] = position
        row["is_overall_top_10"] = position <= 10
    return candidates
