"""CPU-only tests for the configurable repair-cost scenario engine."""

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.src.repair_cost_estimator import (  # noqa: E402
    estimate_detection,
    estimate_severity_report,
    load_pricing_config,
)


PRICING = load_pricing_config(ROOT / "pricing" / "illustrative_repair_pricing.json")


def severity_detection(
    class_name="dent",
    severity="minor",
    detection_id=0,
    evidence_overrides=None,
    human_review=False,
):
    evidence = {
        "detection_id": detection_id,
        "class_id": 0,
        "class_name": class_name,
        "confidence": 0.9,
        "bbox_xyxy": [10, 10, 30, 30],
        "masks_available": True,
        "mask_area_pixels": 100,
    }
    evidence.update(evidence_overrides or {})
    return {
        "original_evidence": evidence,
        "preliminary_severity": severity,
        "severity_reasons": ["test reason"],
        "human_review_required": human_review,
        "human_review_reasons": ["review test reason"] if human_review else [],
    }


class TestPerDetectionEstimates(unittest.TestCase):
    def test_valid_estimate_exposes_assumptions_and_rates(self):
        result = estimate_detection(severity_detection(), PRICING)
        self.assertEqual(result["estimate_status"], "conditional_estimate_available")
        self.assertEqual(result["damage_class"], "dent")
        self.assertEqual(result["preliminary_severity"], "minor")
        self.assertEqual(result["cost_estimate"]["currency"], "USD")
        self.assertTrue(result["cost_estimate"]["human_review_required"])
        self.assertEqual(
            result["cost_estimate"]["assumptions"]["vehicle_component"],
            "unknown; not established by image detection",
        )
        self.assertFalse(result["cost_estimate"]["eligible_for_vehicle_total"])

    def test_missing_pricing_rule_is_not_silently_zero(self):
        pricing = copy.deepcopy(PRICING)
        del pricing["repair_rules"]["dent"]["minor"]
        result = estimate_detection(severity_detection(), pricing)
        self.assertEqual(result["estimate_status"], "not_estimated")
        self.assertIsNone(result["cost_estimate"])
        self.assertTrue(any("No pricing rule" in r for r in result["human_review_reasons"]))

    def test_unknown_damage_class_is_not_estimated(self):
        result = estimate_detection(severity_detection("unknown_damage"), PRICING)
        self.assertEqual(result["estimate_status"], "not_estimated")
        self.assertTrue(any("No pricing rule" in r for r in result["human_review_reasons"]))

    def test_undetermined_severity_is_not_estimated(self):
        result = estimate_detection(severity_detection(severity="undetermined"), PRICING)
        self.assertEqual(result["estimate_status"], "not_estimated")
        self.assertTrue(any("undetermined" in r for r in result["human_review_reasons"]))

    def test_missing_evidence_is_not_estimated(self):
        result = estimate_detection({"preliminary_severity": "minor"}, PRICING)
        self.assertEqual(result["estimate_status"], "not_estimated")
        self.assertTrue(any("Original detector evidence is missing" in r for r in result["human_review_reasons"]))


class TestCostCalculation(unittest.TestCase):
    def test_low_high_calculation_and_explicit_non_applicable_parts(self):
        result = estimate_detection(severity_detection(), PRICING)
        calculation = result["cost_estimate"]["calculation"]
        self.assertEqual(calculation["labor"]["cost_range"], {"low": 45.0, "high": 170.0})
        self.assertFalse(calculation["parts"]["applicable"])
        self.assertEqual(calculation["parts"]["cost_range"], {"low": 0.0, "high": 0.0})
        self.assertEqual(calculation["paint_materials"]["cost_range"], {"low": 25.0, "high": 70.0})
        self.assertEqual(calculation["pre_tax_subtotal"], {"low": 70.0, "high": 240.0})
        self.assertEqual(calculation["total_cost_range"], {"low": 70.0, "high": 240.0})
        self.assertFalse(calculation["tax"]["enabled"])

    def test_configured_tax_is_applied_to_selected_basis(self):
        pricing = copy.deepcopy(PRICING)
        pricing["optional_charges"]["tax"] = {
            "enabled": True,
            "rate": 0.10,
            "applies_to": ["labor", "paint_materials"],
        }
        calculation = estimate_detection(severity_detection(), pricing)["cost_estimate"]["calculation"]
        self.assertEqual(calculation["tax"]["taxable_amount_range"], {"low": 70.0, "high": 240.0})
        self.assertEqual(calculation["tax"]["cost_range"], {"low": 7.0, "high": 24.0})
        self.assertEqual(calculation["total_cost_range"], {"low": 77.0, "high": 264.0})


class TestReportAggregation(unittest.TestCase):
    def test_overlap_is_flagged_and_prevents_summing_a_vehicle_total(self):
        first = severity_detection(detection_id=4)
        second = severity_detection("scratch", detection_id=5)
        report = estimate_severity_report({
            "source_image": "overlap.jpg",
            "assessment_status": "provisional; requires human review",
            "detections": [first, second],
            "overlap_pairs": [{
                "detection_ids": [4, 5], "bbox_iou": 0.7,
                "human_review_required": True,
            }],
        }, PRICING)
        self.assertEqual(report["summary"]["counts"]["overlap_review"], 2)
        self.assertTrue(all(item["human_review_required"] for item in report["estimates"]))
        self.assertIsNone(report["summary"]["vehicle_total"]["low"])
        self.assertTrue(any("overlapping" in r for r in report["summary"]["vehicle_total"]["reasons"]))

    def test_empty_report_does_not_claim_zero_cost(self):
        report = estimate_severity_report({"source_image": "empty.jpg", "detections": []}, PRICING)
        total = report["summary"]["vehicle_total"]
        self.assertEqual(report["summary"]["detection_count"], 0)
        self.assertIsNone(total["low"])
        self.assertIsNone(total["high"])
        self.assertTrue(any("does not establish" in r for r in total["reasons"]))

    def test_report_includes_disclaimer_and_pricing_provenance(self):
        report = estimate_severity_report({"detections": []}, PRICING)
        self.assertIn("not a workshop quotation", report["disclaimer"])
        self.assertIn("invented examples", report["pricing_source_note"])


if __name__ == "__main__":
    unittest.main()
