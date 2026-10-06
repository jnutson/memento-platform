from __future__ import annotations

import hashlib


CONTRACT_VERSION = "memento-retail-v1.1"

SCHEMAS: dict[str, list[tuple[str, str]]] = {
    "calendar_day": [("retail_calendar_id","VARCHAR"),("calendar_date","DATE"),("calendar_day_of_month","UTINYINT"),("calendar_weekday_number","UTINYINT"),("calendar_weekday_name","VARCHAR"),("calendar_month_number","UTINYINT"),("calendar_month_name","VARCHAR"),("calendar_quarter_number","UTINYINT"),("calendar_year","SMALLINT"),("retail_day_number","USMALLINT"),("retail_week_number","UTINYINT"),("retail_month_number","UTINYINT"),("retail_quarter_number","UTINYINT"),("retail_year","SMALLINT"),("retail_year_week","INTEGER"),("comparable_calendar_date","DATE"),("comparable_retail_year_week","INTEGER")],
    "location": [("location_id","VARCHAR"),("source_system","VARCHAR"),("source_company_id","VARCHAR"),("source_location_id","VARCHAR"),("country_code","VARCHAR"),("location_name","VARCHAR"),("source_location_type_code","VARCHAR"),("source_location_type_name","VARCHAR"),("source_status_code","VARCHAR"),("source_status_name","VARCHAR"),("city_name","VARCHAR"),("county_name","VARCHAR"),("state_province_code","VARCHAR"),("state_province_name","VARCHAR"),("postal_code","VARCHAR"),("latitude","DOUBLE"),("longitude","DOUBLE"),("source_region_id","VARCHAR"),("source_region_name","VARCHAR"),("source_market_id","VARCHAR"),("source_market_name","VARCHAR"),("source_timezone_code","VARCHAR"),("timezone_name","VARCHAR")],
    "product": [("product_id","VARCHAR"),("source_system","VARCHAR"),("source_company_id","VARCHAR"),("source_product_id","VARCHAR"),("product_name","VARCHAR"),("product_description","VARCHAR"),("upc","VARCHAR"),("brand_name","VARCHAR"),("source_department_id","VARCHAR"),("source_department_name","VARCHAR"),("source_category_id","VARCHAR"),("source_category_name","VARCHAR"),("source_subcategory_id","VARCHAR"),("source_subcategory_name","VARCHAR"),("source_fineline_id","VARCHAR"),("source_fineline_name","VARCHAR"),("source_season_code","VARCHAR"),("source_status_code","VARCHAR"),("effective_date","DATE"),("replenishment_enabled","BOOLEAN"),("unit_of_measure_code","VARCHAR"),("base_unit_retail_amount","DECIMAL(20,2)"),("currency_code","VARCHAR"),("source_item_type_code","VARCHAR"),("source_replenishment_type_code","VARCHAR")],
    "sales_daily": [("business_date","DATE"),("retail_calendar_id","VARCHAR"),("retail_year_week","INTEGER"),("location_id","VARCHAR"),("product_id","VARCHAR"),("retail_type_code","VARCHAR"),("sales_channel_code","VARCHAR"),("sales_quantity","BIGINT"),("sales_amount","DECIMAL(20,2)"),("source_comparison_quantity","BIGINT"),("source_comparison_amount","DECIMAL(20,2)"),("currency_code","VARCHAR")],
    "inventory_daily": [("business_date","DATE"),("retail_calendar_id","VARCHAR"),("retail_year_week","INTEGER"),("location_id","VARCHAR"),("product_id","VARCHAR"),("currency_code","VARCHAR"),("source_merchandise_family_id","VARCHAR"),("on_hand_quantity","BIGINT"),("source_comparison_on_hand_quantity","BIGINT"),("on_hand_retail_amount","DECIMAL(20,2)"),("source_comparison_on_hand_retail_amount","DECIMAL(20,2)"),("on_order_quantity","BIGINT"),("source_comparison_on_order_quantity","BIGINT"),("in_transit_quantity","BIGINT"),("source_comparison_in_transit_quantity","BIGINT"),("receipt_quantity","BIGINT"),("source_comparison_receipt_quantity","BIGINT"),("maximum_shelf_quantity","BIGINT"),("source_comparison_maximum_shelf_quantity","BIGINT"),("assorted","BOOLEAN"),("source_comparison_assorted","BOOLEAN"),("replenishment_enabled","BOOLEAN"),("source_comparison_replenishment_enabled","BOOLEAN"),("current_unit_retail_amount","DECIMAL(20,2)")],
    "demand_forecast_weekly": [("retail_calendar_id","VARCHAR"),("forecast_created_retail_year_week","INTEGER"),("target_retail_year_week","INTEGER"),("location_id","VARCHAR"),("product_id","VARCHAR"),("forecast_quantity","DECIMAL(20,6)")],
    "company_item": [("company_id","VARCHAR"),("company_item_id","VARCHAR"),("company_item_name","VARCHAR"),("display_brand_id","VARCHAR"),("product_id","VARCHAR"),("source_company_id","VARCHAR"),("source_product_id","VARCHAR"),("effective_from","DATE"),("effective_to","DATE")],
    "replenishment_commitment": [("retailer_order_id","VARCHAR"),("order_line_number","INTEGER"),("event_version","INTEGER"),("location_id","VARCHAR"),("product_id","VARCHAR"),("ordered_quantity","BIGINT"),("invoiced_quantity","BIGINT"),("received_quantity","BIGINT"),("order_created_at","TIMESTAMP WITH TIME ZONE"),("approved_to_ship_at","TIMESTAMP WITH TIME ZONE"),("dc_invoiced_at","TIMESTAMP WITH TIME ZONE"),("expected_store_receipt_date","DATE"),("actual_store_receipt_at","TIMESTAMP WITH TIME ZONE"),("status_code","VARCHAR"),("known_at","TIMESTAMP WITH TIME ZONE")],
    "reaction_constraint": [("company_id","VARCHAR"),("item_scope_type_code","VARCHAR"),("item_scope_id","VARCHAR"),("minimum_reaction_days","INTEGER"),("effective_from","DATE"),("effective_to","DATE")],
    "company_item_economics": [("company_id","VARCHAR"),("company_item_id","VARCHAR"),("currency_code","VARCHAR"),("unit_cost_amount","DECIMAL(20,2)"),("effective_from","DATE"),("effective_to","DATE")],
}


def _lexical_int(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("identifier components must be nonnegative integers")
    return str(value)


def stable_id(kind: str, company: int, source_id: int) -> str:
    if kind not in {"location", "product"}:
        raise ValueError("unsupported identifier kind")
    prefix = "loc" if kind == "location" else "prd"
    preimage = "|".join(
        ["memento", "v1", kind, "walmart", _lexical_int(company), _lexical_int(source_id)]
    )
    return f"{prefix}_{hashlib.sha256(preimage.encode('utf-8')).hexdigest()}"
