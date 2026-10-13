"""Conditional repair-cost scenarios from preliminary severity JSON reports.

Prices are read only from an explicit rate card. The bundled rate card is
illustrative, not market data. Estimates are conditional on stated repair
scenarios; this module never infers a vehicle component or necessary repair.
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRICING_PATH = PROJECT_ROOT / "pricing" / "illustrative_repair_pricing.json"
DEFAULT_OUTPUT_DIR = Path("outputs/repair_costs")
SUPPORTED_SEVERITIES = {"minor", "moderate", "major"}

DISCLAIMER = (
    "This image-based conditional estimate is not a workshop quotation or an "
    "insurance-approved amount. It cannot reveal hidden damage and requires "
    "confirmation by a qualified assessor and local repair shop. The detected "
    "class does not establish the vehicle component or necessary repair method."
)


class PricingConfigurationError(ValueError):
    """Raised when a pricing file is missing required configuration."""


def _decimal(value, field_name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PricingConfigurationError(f"Missing or invalid price value: {field_name}") from exc
    if not result.is_finite() or result < 0:
        raise PricingConfigurationError(f"Price value must be finite and non-negative: {field_name}")
    return result


def _money(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _price_range(value, field_name):
    if not isinstance(value, dict) or "low" not in value or "high" not in value:
        raise PricingConfigurationError(f"Missing low/high price range: {field_name}")
    low = _decimal(value["low"], f"{field_name}.low")
    high = _decimal(value["high"], f"{field_name}.high")
    if low > high:
        raise PricingConfigurationError(f"Low price exceeds high price: {field_name}")
    return low, high


def load_pricing_config(path: str | Path = DEFAULT_PRICING_PATH) -> dict:
    """Load explicit pricing data; never invent fallback rates."""
    price_path = Path(path)
    try:
        config = json.loads(price_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PricingConfigurationError(f"Cannot load pricing file {price_path}: {exc}") from exc
    if not isinstance(config, dict):
        raise PricingConfigurationError("Pricing file must contain a JSON object.")
    for key in ("currency", "pricing_status", "labor_rates_per_hour", "optional_charges", "repair_rules"):
        if key not in config:
            raise PricingConfigurationError(f"Pricing configuration is missing {key!r}.")
    if not isinstance(config["currency"], str) or not config["currency"].strip():
        raise PricingConfigurationError("Pricing currency must be a non-empty string.")
    if not isinstance(config["labor_rates_per_hour"], dict):
        raise PricingConfigurationError("labor_rates_per_hour must be an object.")
    if not isinstance(config["repair_rules"], dict):
        raise PricingConfigurationError("repair_rules must be an object.")
    optional = config["optional_charges"]
    if not isinstance(optional, dict) or "miscellaneous" not in optional or "tax" not in optional:
        raise PricingConfigurationError(
            "optional_charges must explicitly configure miscellaneous and tax settings."
        )
    for charge_name in ("miscellaneous", "tax"):
        if not isinstance(optional[charge_name], dict) or "enabled" not in optional[charge_name]:
            raise PricingConfigurationError(f"{charge_name} must explicitly set enabled.")
    tax = optional["tax"]
    if tax["enabled"]:
        if "rate" not in tax or "applies_to" not in tax:
            raise PricingConfigurationError("Enabled tax requires an explicit rate and applies_to list.")
        rate = float(_decimal(tax["rate"], "optional_charges.tax.rate"))
        if rate > 1:
            raise PricingConfigurationError("Tax rate must be a fraction between 0 and 1.")
        if not isinstance(tax["applies_to"], list):
            raise PricingConfigurationError("Tax applies_to must be a list.")
    misc = optional["miscellaneous"]
    if misc["enabled"]:
        _price_range(misc.get("cost_range"), "optional_charges.miscellaneous.cost_range")
    return config


def _component_cost(item, field_name):
    """Read explicit applicable/not-applicable parts or material charges."""
    if not isinstance(item, dict) or "applicable" not in item:
        raise PricingConfigurationError(f"{field_name} must explicitly set applicable.")
    if not item["applicable"]:
        return {
            "applicable": False,
            "description": item.get("description", "Explicitly excluded by pricing rule."),
            "cost_range": {"low": 0.0, "high": 0.0},
        }, (Decimal(0), Decimal(0))
    cost = _price_range(item.get("cost_range"), f"{field_name}.cost_range")
    return {
        "applicable": True,
        "description": item.get("description", ""),
        "cost_range": {"low": _money(cost[0]), "high": _money(cost[1])},
    }, cost


def _calculate_scenario(rule: dict, config: dict):
    """Calculate labor, parts, materials, misc and tax from explicit ranges."""
    category = rule.get("labor_category")
    if not category or category not in config["labor_rates_per_hour"]:
        raise PricingConfigurationError(f"Missing labor rate for category {category!r}.")
    rate_low, rate_high = _price_range(
        config["labor_rates_per_hour"][category], f"labor_rates_per_hour.{category}"
    )
    hour_low, hour_high = _price_range(rule.get("labor_hours"), "repair_rule.labor_hours")
    labor_low, labor_high = rate_low * hour_low, rate_high * hour_high

    parts_item, parts_range = _component_cost(rule.get("parts"), "repair_rule.parts")
    paint_item, paint_range = _component_cost(
        rule.get("paint_materials"), "repair_rule.paint_materials"
    )

    optional = config["optional_charges"]
    misc_config = optional["miscellaneous"]
    if misc_config["enabled"]:
        misc_range = _price_range(misc_config.get("cost_range"), "optional_charges.miscellaneous.cost_range")
        misc_item = {
            "enabled": True,
            "description": misc_config.get("description", ""),
            "cost_range": {"low": _money(misc_range[0]), "high": _money(misc_range[1])},
        }
    else:
        misc_range = (Decimal(0), Decimal(0))
        misc_item = {
            "enabled": False,
            "description": misc_config.get("description", ""),
            "cost_range": {"low": 0.0, "high": 0.0},
        }

    components = {
        "labor": (labor_low, labor_high),
        "parts": parts_range,
        "paint_materials": paint_range,
        "miscellaneous": misc_range,
    }
    subtotal_low = sum((span[0] for span in components.values()), Decimal(0))
    subtotal_high = sum((span[1] for span in components.values()), Decimal(0))
    tax_config = optional["tax"]
    if tax_config["enabled"]:
        tax_rate = _decimal(tax_config["rate"], "optional_charges.tax.rate")
        basis = tax_config["applies_to"]
        unknown_basis = set(basis) - set(components)
        if unknown_basis:
            raise PricingConfigurationError(f"Unknown tax basis item(s): {sorted(unknown_basis)}")
        taxable_low = sum((components[name][0] for name in basis), Decimal(0))
        taxable_high = sum((components[name][1] for name in basis), Decimal(0))
        tax_low, tax_high = taxable_low * tax_rate, taxable_high * tax_rate
    else:
        tax_rate = Decimal(0)
        taxable_low = taxable_high = tax_low = tax_high = Decimal(0)

    total_low, total_high = subtotal_low + tax_low, subtotal_high + tax_high
    return {
        "labor": {
            "category": category,
            "hourly_rate_range": {"low": _money(rate_low), "high": _money(rate_high)},
            "estimated_hours_range": {"low": _money(hour_low), "high": _money(hour_high)},
            "cost_range": {"low": _money(labor_low), "high": _money(labor_high)},
            "formula": "labor hours × hourly rate; low uses low values and high uses high values",
        },
        "parts": parts_item,
        "paint_materials": paint_item,
        "miscellaneous": misc_item,
        "pre_tax_subtotal": {"low": _money(subtotal_low), "high": _money(subtotal_high)},
        "tax": {
            "enabled": bool(tax_config["enabled"]),
            "rate": float(tax_rate),
            "applies_to": list(tax_config.get("applies_to", [])),
            "taxable_amount_range": {"low": _money(taxable_low), "high": _money(taxable_high)},
            "cost_range": {"low": _money(tax_low), "high": _money(tax_high)},
        },
        "total_cost_range": {"low": _money(total_low), "high": _money(total_high)},
    }


def _overlap_detection_ids(report: dict):
    detection_ids = set()
    for pair in report.get("overlap_pairs", []) or []:
        if not isinstance(pair, dict):
            continue
        ids = pair.get("detection_ids", [])
        if pair.get("human_review_required") and isinstance(ids, list):
            detection_ids.update(ids)
    return detection_ids


def estimate_detection(
    severity_detection: dict,
    pricing_config: dict,
    overlapping_detection_ids=None,
) -> dict:
    """Estimate one detection conditionally, or explain why it is withheld."""
    overlapping_detection_ids = overlapping_detection_ids or set()
    evidence = severity_detection.get("original_evidence")
    detection_id = evidence.get("detection_id") if isinstance(evidence, dict) else None
    damage_class = evidence.get("class_name") if isinstance(evidence, dict) else None
    severity = severity_detection.get("preliminary_severity")
    review_reasons = list(severity_detection.get("human_review_reasons") or [])
    blockers = []
    if not isinstance(evidence, dict):
        blockers.append("Original detector evidence is missing; a cost scenario cannot be tied to a detection.")
    elif not damage_class:
        blockers.append("Damage class is missing from original detector evidence.")
    confidence = evidence.get("confidence") if isinstance(evidence, dict) else None
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = None
    if confidence_value is None or not math.isfinite(confidence_value):
        blockers.append("Detection confidence is missing or invalid; detection reliability cannot be checked.")
    if severity == "undetermined":
        blockers.append("Severity is undetermined; no severity-based cost rule can be selected.")
    elif severity not in SUPPORTED_SEVERITIES:
        blockers.append(f"Unsupported or missing severity label {severity!r}; no pricing rule selected.")

    normalized_class = str(damage_class).strip().lower() if damage_class else ""
    rules = pricing_config.get("repair_rules", {})
    class_rules = rules.get(normalized_class) if isinstance(rules, dict) else None
    rule = class_rules.get(severity) if isinstance(class_rules, dict) and severity in SUPPORTED_SEVERITIES else None
    if not isinstance(rule, dict):
        blockers.append(
            f"No pricing rule is configured for damage class {normalized_class!r} "
            f"and severity {severity!r}."
        )

    estimate = None
    if not blockers:
        try:
            calculation = _calculate_scenario(rule, pricing_config)
        except PricingConfigurationError as exc:
            blockers.append(str(exc))
        else:
            component = evidence.get("confirmed_vehicle_component") if isinstance(evidence, dict) else None
            action_confirmed = bool(evidence.get("confirmed_repair_action")) if isinstance(evidence, dict) else False
            action_uncertain = bool(rule.get("action_uncertain", True))
            severity_reviewed = severity_detection.get("severity_reviewed") is True
            if not severity_reviewed:
                review_reasons.append(
                    "Severity remains provisional; confirm the label before treating this as a workshop scope."
                )
            if not component:
                review_reasons.append(
                    "Vehicle component is unknown; the class label does not identify the damaged part."
                )
            if action_uncertain or not action_confirmed:
                review_reasons.append(
                    "Repair method is an illustrative scenario, not a finding that this repair is necessary."
                )
            if severity_detection.get("human_review_required", True):
                review_reasons.append("Severity assessment is provisional and marked for human review.")
            is_overlap = detection_id in overlapping_detection_ids
            if is_overlap:
                review_reasons.append(
                    "This detection overlaps another possible finding; do not add both line estimates until a reviewer confirms they are distinct."
                )
            review_reasons = list(dict.fromkeys(review_reasons))
            estimate = {
                "currency": pricing_config["currency"],
                "estimate_type": "conditional illustrative repair scenario; not a quote",
                "estimate_range": calculation["total_cost_range"],
                "calculation": calculation,
                "assumptions": {
                    "scenario_name": rule.get("scenario_name", "Configured repair scenario"),
                    "action_assumption": rule.get("action_assumption", "No action description provided."),
                    "vehicle_component": component or "unknown; not established by image detection",
                    "repair_method_confirmed": action_confirmed,
                    "repair_method_uncertain": action_uncertain or not action_confirmed,
                    "severity_is_provisional": not severity_reviewed,
                    "overlap_may_duplicate_cost": is_overlap,
                },
                "human_review_required": bool(review_reasons),
                "human_review_reasons": review_reasons,
                "eligible_for_vehicle_total": not review_reasons,
            }

    if blockers:
        review_reasons.extend(blockers)
    review_reasons = list(dict.fromkeys(review_reasons))
    return {
        "detection_id": detection_id,
        "damage_class": damage_class,
        "preliminary_severity": severity,
        "original_evidence": evidence,
        "estimate_status": "conditional_estimate_available" if estimate else "not_estimated",
        "cost_estimate": estimate,
        "human_review_required": True if blockers else estimate["human_review_required"],
        "human_review_reasons": review_reasons,
    }


def estimate_severity_report(
    severity_report: dict,
    pricing_config: dict,
    source_severity_file: str | Path | None = None,
    pricing_file: str | Path | None = None,
) -> dict:
    """Build a report with per-detection scenario ranges and a gated vehicle total."""
    if not isinstance(severity_report, dict):
        raise ValueError("Severity report must be a JSON object.")
    detections = severity_report.get("detections")
    if not isinstance(detections, list):
        raise ValueError("Severity report must contain a 'detections' list.")
    overlapping_ids = _overlap_detection_ids(severity_report)
    estimates = []
    for index, detection in enumerate(detections):
        if not isinstance(detection, dict):
            raise ValueError(f"Severity detection at index {index} must be a JSON object.")
        item = estimate_detection(detection, pricing_config, overlapping_ids)
        if item["detection_id"] is None:
            item["detection_id"] = index
        estimates.append(item)

    total_blockers = []
    if not estimates:
        total_blockers.append(
            "No detections were reported; this does not establish that the vehicle has no damage or repair cost."
        )
    if severity_report.get("assessment_status") != "reviewed":
        total_blockers.append("Severity report is provisional or is not explicitly marked reviewed.")
    if overlapping_ids:
        total_blockers.append(
            "Potentially overlapping detections may describe the same physical damage; do not sum those line estimates."
        )
    if any(item["estimate_status"] != "conditional_estimate_available" for item in estimates):
        total_blockers.append("One or more detections lack a usable estimate; a complete total is unavailable.")
    if any(item["human_review_required"] for item in estimates):
        total_blockers.append("One or more estimates or severity decisions require human review.")
    if any(
        item["cost_estimate"]
        and (
            item["cost_estimate"]["assumptions"]["vehicle_component"].startswith("unknown")
            or item["cost_estimate"]["assumptions"]["repair_method_uncertain"]
        )
        for item in estimates
    ):
        total_blockers.append("Vehicle component or necessary repair method is not confirmed.")
    total_blockers = list(dict.fromkeys(total_blockers))

    vehicle_total = {"currency": pricing_config["currency"]}
    if not total_blockers:
        low = sum(
            item["cost_estimate"]["estimate_range"]["low"] for item in estimates
        )
        high = sum(
            item["cost_estimate"]["estimate_range"]["high"] for item in estimates
        )
        vehicle_total.update({
            "status": "provisional_range_supported_by_reviewed_inputs",
            "low": round(low, 2),
            "high": round(high, 2),
            "human_review_required": False,
            "reasons": [],
        })
    else:
        vehicle_total.update({
            "status": "not_provided_insufficient_or_unreviewed_information",
            "low": None,
            "high": None,
            "human_review_required": True,
            "reasons": total_blockers,
        })

    counts = {
        "conditional_estimate_available": sum(
            item["estimate_status"] == "conditional_estimate_available" for item in estimates
        ),
        "not_estimated": sum(item["estimate_status"] == "not_estimated" for item in estimates),
        "human_review_required": sum(item["human_review_required"] for item in estimates),
        "overlap_review": sum(item["detection_id"] in overlapping_ids for item in estimates),
    }
    return {
        "report_type": "conditional_image_based_repair_cost_estimate",
        "source_image": severity_report.get("source_image"),
        "source_severity_file": str(source_severity_file) if source_severity_file else None,
        "pricing_file": str(pricing_file) if pricing_file else None,
        "pricing_status": pricing_config.get("pricing_status"),
        "currency": pricing_config["currency"],
        "source_severity_status": severity_report.get("assessment_status"),
        "estimates": estimates,
        "summary": {
            "detection_count": len(estimates),
            "counts": counts,
            "vehicle_total": vehicle_total,
        },
        "pricing_source_note": pricing_config.get(
            "rate_source_note", "Pricing source note was not provided. Verify all rates locally."
        ),
        "disclaimer": DISCLAIMER,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


def _read_json_object(path: Path, description: str):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {description} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{description.capitalize()} must contain a JSON object: {path}")
    return value


def parse_args():
    parser = argparse.ArgumentParser(
        description="Estimate conditional cost ranges from severity assessment JSON."
    )
    parser.add_argument("severity_json", nargs="+", help="Severity report JSON file(s).")
    parser.add_argument("--pricing", default=str(DEFAULT_PRICING_PATH), help="Pricing JSON rate card.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        pricing = load_pricing_config(args.pricing)
    except PricingConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    output_dir = Path(args.output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Error: cannot create output directory {output_dir}: {exc}", file=sys.stderr)
        return 1

    failures = 0
    for input_name in args.severity_json:
        input_path = Path(input_name)
        try:
            severity_report = _read_json_object(input_path, "severity report")
            report = estimate_severity_report(
                severity_report, pricing, input_path, args.pricing
            )
            output_path = output_dir / f"{input_path.stem}_repair_cost.json"
            output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except (ValueError, OSError) as exc:
            print(f"Error [{input_path}]: {exc}", file=sys.stderr)
            failures += 1
            continue
        total = report["summary"]["vehicle_total"]
        print(
            f"{input_path}: {report['summary']['counts']['conditional_estimate_available']} "
            f"conditional line estimate(s); vehicle total: {total['status']}."
        )
        print(f"Saved estimate report: {output_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
