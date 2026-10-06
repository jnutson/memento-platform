# Canonical Retail Contract V1

Status: accepted design contract for the ingestion MVP
Contract version: `memento-retail-v1.1`
Physical format: Parquet queried with DuckDB

## Purpose

This document fixes the canonical schema decisions required to implement the first
Walmart-shaped ingestion adapter. Downstream analytics depend on these Memento-owned
tables rather than retailer column names.

The contract preserves source grain, uses deterministic identifiers, and keeps
dataset lineage in the release manifest rather than duplicating it on every fact row.
All columns are required unless explicitly marked nullable.

V1.1 adds the physically distinct `company_item_economics` canonical dataset with
`company_id`, `company_item_id`, `currency_code`, `unit_cost_amount`, `effective_from`,
and nullable `effective_to`. Publication fails on missing, overlapping, negative,
non-USD, or unmapped effective rows. It is never joined into raw retailer facts.

## Type conventions

| Logical type | DuckDB / Parquet representation | Rule |
|---|---|---|
| Canonical identifier | `VARCHAR` | Lowercase prefixed SHA-256 identifier |
| Source identifier/code | `VARCHAR` | Preserve lexical value; never infer numeric meaning |
| Calendar date | `DATE` | ISO calendar date |
| Retail year-week | `INTEGER` | `YYYYWW`; week must resolve through `calendar_day` |
| Whole-unit quantity | `BIGINT` | Signed; negative values are preserved, not repaired |
| Fractional quantity | `DECIMAL(20,6)` | Used for forecasts |
| Currency amount | `DECIMAL(20,2)` | ISO currency minor-unit precision for this contract |
| Coordinate | `DOUBLE` | Finite and within geographic bounds |
| Boolean | `BOOLEAN` | Never encoded as string or integer |
| Enumerated value | `VARCHAR` | Must belong to the field's versioned domain |

The Walmart source represents money as floating point. Before conversion, the adapter
must verify that each value is finite and equals its two-decimal rounding within
`0.000001`. It may then cast the rounded value to `DECIMAL(20,2)`. A value outside that
tolerance fails canonicalization; it is not silently rounded.

## Deterministic identifiers

Identifiers use the UTF-8 SHA-256 digest of an unambiguous canonical preimage:

```text
location preimage = "memento|v1|location|walmart|<company>|<location>"
product preimage  = "memento|v1|product|walmart|<company>|<product>"

location_id = "loc_" + lowercase_hex(sha256(location preimage))
product_id  = "prd_" + lowercase_hex(sha256(product preimage))
```

`<company>`, `<location>`, and `<product>` are the base-10 lexical forms of the
validated source integers with no sign, grouping, whitespace, or leading zeroes,
except the value zero is encoded as `0`. The full 64-character digest is retained.

IDs are independent of row order, run ID, timestamps, and filesystem location. The
canonical source identifiers are retained alongside them for audit and joins back to
the source release.

## Enumerations

### Shared domains

| Field | V1 allowed values |
|---|---|
| `source_system` | `walmart` |
| `country_code` | `US` |
| `currency_code` | `USD` |
| `retail_calendar_id` | `walmart-us-454` |

### Sales domains

The Walmart adapter maps `rpt_cd` as follows:

| Walmart `rpt_cd` | `retail_type_code` |
|---:|---|
| `0` | `regular` |
| `7` | `rollback` |
| `8` | `clearance` |

Any other value is a source-validation failure for adapter V1.

`svc_chnl_nm` maps to `sales_channel_code` by trimming neither content nor case. V1
allows only `BIS`, which remains a namespaced source-domain value until its business
meaning is formally defined. Any other value fails source validation rather than being
collapsed into an `other` category.

Dimension status/type/code values not listed above remain retailer-domain values in
explicitly named `source_*` columns. They are not presented as universal Memento
enumerations.

## `calendar_day`

Grain and primary key:

```text
(retail_calendar_id, calendar_date)
```

| Column | Type | Nullable | Source |
|---|---|---:|---|
| `retail_calendar_id` | `VARCHAR` | no | constant `walmart-us-454` |
| `calendar_date` | `DATE` | no | `cal_dt` |
| `calendar_day_of_month` | `UTINYINT` | no | `cal_day_nbr` |
| `calendar_weekday_number` | `UTINYINT` | no | `cal_wk_day_nbr` |
| `calendar_weekday_name` | `VARCHAR` | no | `cal_wk_day_nm` |
| `calendar_month_number` | `UTINYINT` | no | `cal_mth_nbr` |
| `calendar_month_name` | `VARCHAR` | no | `cal_mth_nm` |
| `calendar_quarter_number` | `UTINYINT` | no | `cal_qtr_nbr` |
| `calendar_year` | `SMALLINT` | no | `cal_full_yr_nbr` |
| `retail_day_number` | `USMALLINT` | no | `wm_day_nbr` |
| `retail_week_number` | `UTINYINT` | no | `wm_week_nbr` |
| `retail_month_number` | `UTINYINT` | no | `wm_mth_nbr` |
| `retail_quarter_number` | `UTINYINT` | no | `wm_qtr_nbr` |
| `retail_year` | `SMALLINT` | no | `wm_yr_nbr` |
| `retail_year_week` | `INTEGER` | no | `wm_yr_wk_nbr` |
| `comparable_calendar_date` | `DATE` | no | `ly_comp_visit_dt` |
| `comparable_retail_year_week` | `INTEGER` | no | `ly_comp_yr_wk_nbr` |

The redundant source fields `fiscal_*` and `ly_cal_dt` are not published in V1. Their
declared equivalence to the selected calendar concepts must be validated before they
are dropped.

Required ranges include weekday `1..7`, month `1..12`, quarter `1..4`, and retail week
`1..53`. `retail_year_week` must equal `retail_year * 100 + retail_week_number`.

## `location`

Primary key: `location_id`.

| Column | Type | Nullable | Source |
|---|---|---:|---|
| `location_id` | `VARCHAR` | no | deterministic ID |
| `source_system` | `VARCHAR` | no | constant `walmart` |
| `source_company_id` | `VARCHAR` | no | constant `0`; `store_dim` omits company |
| `source_location_id` | `VARCHAR` | no | lexical `store_nbr` |
| `country_code` | `VARCHAR` | no | `geo_region_cd` mapped to `US` |
| `location_name` | `VARCHAR` | no | `store_nm` |
| `source_location_type_code` | `VARCHAR` | no | `store_type_cd` |
| `source_location_type_name` | `VARCHAR` | no | `store_type_desc` |
| `source_status_code` | `VARCHAR` | no | `open_status_cd` |
| `source_status_name` | `VARCHAR` | no | `open_status_desc` |
| `city_name` | `VARCHAR` | no | `city_nm` |
| `county_name` | `VARCHAR` | no | `cnty_nm` |
| `state_province_code` | `VARCHAR` | no | `state_prov_cd` |
| `state_province_name` | `VARCHAR` | no | `st_prov_nm` |
| `postal_code` | `VARCHAR` | no | `postal_cd` |
| `latitude` | `DOUBLE` | no | `lat_dgr` |
| `longitude` | `DOUBLE` | no | `long_dgr` |
| `source_region_id` | `VARCHAR` | no | lexical `region_nbr` |
| `source_region_name` | `VARCHAR` | no | `region_nm` |
| `source_market_id` | `VARCHAR` | no | lexical `market_nbr` |
| `source_market_name` | `VARCHAR` | no | `market_nm` |
| `source_timezone_code` | `VARCHAR` | no | `tz_cd` |
| `timezone_name` | `VARCHAR` | no | `tz_nm`; valid IANA name |

Candidate key `(source_system, source_company_id, source_location_id)` must be unique.
Latitude must be within `[-90, 90]` and longitude within `[-180, 180]`.
Every fact row that resolves to this V1 location must have `op_cmpny_cd = 0`; any other
company value fails validation because `store_dim` cannot disambiguate it.

## `product`

Primary key: `product_id`.

| Column | Type | Nullable | Source |
|---|---|---:|---|
| `product_id` | `VARCHAR` | no | deterministic ID |
| `source_system` | `VARCHAR` | no | constant `walmart` |
| `source_company_id` | `VARCHAR` | no | lexical `op_cmpny_cd` |
| `source_product_id` | `VARCHAR` | no | lexical `wm_item_nbr` |
| `product_name` | `VARCHAR` | no | `item_nm` |
| `product_description` | `VARCHAR` | no | `item_desc` |
| `upc` | `VARCHAR` | no | `upc_nbr`; lexical value preserved |
| `brand_name` | `VARCHAR` | no | `brand_nm` |
| `source_department_id` | `VARCHAR` | no | lexical `omni_dept_nbr` |
| `source_department_name` | `VARCHAR` | no | `omni_dept_desc` |
| `source_category_id` | `VARCHAR` | no | lexical `omni_catg_nbr` |
| `source_category_name` | `VARCHAR` | no | `omni_catg_desc` |
| `source_subcategory_id` | `VARCHAR` | no | lexical `omni_subcatg_nbr` |
| `source_subcategory_name` | `VARCHAR` | no | `omni_subcatg_desc` |
| `source_fineline_id` | `VARCHAR` | no | lexical `fineline_nbr` |
| `source_fineline_name` | `VARCHAR` | no | `fineline_desc` |
| `source_season_code` | `VARCHAR` | no | `season_cd` |
| `source_status_code` | `VARCHAR` | no | `item_status_cd` |
| `effective_date` | `DATE` | no | `item_effective_dt` |
| `replenishment_enabled` | `BOOLEAN` | no | `item_repl_ind` |
| `unit_of_measure_code` | `VARCHAR` | no | `retail_uom_cd` |
| `base_unit_retail_amount` | `DECIMAL(20,2)` | no | validated `base_unit_rtl_amt` |
| `currency_code` | `VARCHAR` | no | constant `USD` |
| `source_item_type_code` | `VARCHAR` | no | `item_type_cd` |
| `source_replenishment_type_code` | `VARCHAR` | no | `repl_type_cd` |

Candidate key `(source_system, source_company_id, source_product_id)` and `upc` must be
unique in adapter V1. Monetary amounts must be nonnegative.

## `sales_daily`

Primary key and grain:

```text
(business_date, location_id, product_id, retail_type_code, sales_channel_code)
```

| Column | Type | Nullable | Source |
|---|---|---:|---|
| `business_date` | `DATE` | no | `bus_dt` |
| `retail_calendar_id` | `VARCHAR` | no | constant `walmart-us-454` |
| `retail_year_week` | `INTEGER` | no | `wm_yr_wk_nbr` |
| `location_id` | `VARCHAR` | no | deterministic from company/store |
| `product_id` | `VARCHAR` | no | deterministic from company/item |
| `retail_type_code` | `VARCHAR` | no | mapped `rpt_cd` |
| `sales_channel_code` | `VARCHAR` | no | validated `svc_chnl_nm` |
| `sales_quantity` | `BIGINT` | no | `ty_qty` |
| `sales_amount` | `DECIMAL(20,2)` | no | validated `ty_sales_amt` |
| `source_comparison_quantity` | `BIGINT` | no | `ly_qty` |
| `source_comparison_amount` | `DECIMAL(20,2)` | no | validated `ly_sales_amt` |
| `currency_code` | `VARCHAR` | no | constant `USD` |

Quantities and amounts are signed to preserve returns or corrections. V1 does not infer
return semantics. Dates and weeks must resolve to `calendar_day`; IDs must resolve to
their dimensions.

## `inventory_daily`

Primary key and grain:

```text
(business_date, location_id, product_id)
```

| Column | Type | Nullable | Source |
|---|---|---:|---|
| `business_date` | `DATE` | no | `bus_dt` |
| `retail_calendar_id` | `VARCHAR` | no | constant `walmart-us-454` |
| `retail_year_week` | `INTEGER` | no | `wm_yr_wk_nbr` |
| `location_id` | `VARCHAR` | no | deterministic from company/store |
| `product_id` | `VARCHAR` | no | deterministic from company/item |
| `currency_code` | `VARCHAR` | no | `crncy_cd`; V1 requires `USD` |
| `source_merchandise_family_id` | `VARCHAR` | no | `mds_fam_id` |
| `on_hand_quantity` | `BIGINT` | no | `ty_on_hand_qty` |
| `source_comparison_on_hand_quantity` | `BIGINT` | no | `ly_on_hand_qty` |
| `on_hand_retail_amount` | `DECIMAL(20,2)` | no | `ty_on_hand_rtl_amt` |
| `source_comparison_on_hand_retail_amount` | `DECIMAL(20,2)` | no | `ly_on_hand_rtl_amt` |
| `on_order_quantity` | `BIGINT` | no | `ty_on_order_qty` |
| `source_comparison_on_order_quantity` | `BIGINT` | no | `ly_on_order_qty` |
| `in_transit_quantity` | `BIGINT` | no | `ty_in_transit_qty` |
| `source_comparison_in_transit_quantity` | `BIGINT` | no | `ly_in_transit_qty` |
| `receipt_quantity` | `BIGINT` | no | `ty_rcpt_qty` |
| `source_comparison_receipt_quantity` | `BIGINT` | no | `ly_rcpt_qty` |
| `maximum_shelf_quantity` | `BIGINT` | no | `ty_max_shelf_qty` |
| `source_comparison_maximum_shelf_quantity` | `BIGINT` | no | `ly_max_shelf_qty` |
| `assorted` | `BOOLEAN` | no | `ty_traited_ind` |
| `source_comparison_assorted` | `BOOLEAN` | no | `ly_traited_ind` |
| `replenishment_enabled` | `BOOLEAN` | no | `ty_repl_ind` |
| `source_comparison_replenishment_enabled` | `BOOLEAN` | no | `ly_repl_ind` |
| `current_unit_retail_amount` | `DECIMAL(20,2)` | no | `curr_store_unit_rtl_amt` |

Inventory quantities remain signed because real feeds may represent adjustments. V1
does not infer missing inventory-flow terms or clamp negative values. Monetary values
and the current unit retail amount must be nonnegative.

## `demand_forecast_weekly`

Primary key and grain:

```text
(forecast_created_retail_year_week, target_retail_year_week, location_id, product_id)
```

| Column | Type | Nullable | Source |
|---|---|---:|---|
| `retail_calendar_id` | `VARCHAR` | no | constant `walmart-us-454` |
| `forecast_created_retail_year_week` | `INTEGER` | no | `fcst_wm_yr_wk_nbr` |
| `target_retail_year_week` | `INTEGER` | no | `wm_yr_wk_nbr` |
| `location_id` | `VARCHAR` | no | deterministic from company/store |
| `product_id` | `VARCHAR` | no | deterministic from company/item |
| `forecast_quantity` | `DECIMAL(20,6)` | no | validated `final_fcst_each_qty` |

Both week values must resolve through `calendar_day`, creation week must not follow
target week, and forecast quantity must be finite and nonnegative.

## Lineage contract

Row-level lineage columns are deliberately excluded from V1 because the transformations
preserve grain and a release is immutable. The Memento dataset manifest must record:

- Memento dataset ID and `memento-retail-v1` contract version.
- Trusted Memento source classification.
- Source manifest path, SHA-256, release ID, and declared `as_of`.
- Adapter, transformation, and validation contract versions.
- Source-to-canonical dataset mapping.
- Validation results and rule versions.
- Each canonical file's path, SHA-256, bytes, rows, and date/week bounds.

Source classification comes from trusted Memento run configuration and must not be
inferred solely from an external manifest.

## Compatibility and evolution

- The contract version is part of the published dataset identity.
- The validation contract version is also part of that identity.
- Adding, removing, renaming, retyping, or changing nullability or meaning of a column
  requires a new canonical contract version.
- Expanding a closed enumeration requires an adapter and validation-contract version
  change; it does not silently change an existing release.
- Reordering columns or changing Parquet layout without changing logical content may be
  a transformation-version change.
- Published V1 datasets are immutable and are never rewritten in place.

## Required implementation artifacts

The builder must encode this document in executable schema definitions and tests. Tests
must compare exact names, order, types, and nullability; verify identifier test vectors;
exercise every enumeration mapping; and reject unapproved schema drift.
