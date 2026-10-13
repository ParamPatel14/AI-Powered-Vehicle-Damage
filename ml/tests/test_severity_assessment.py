"""CPU-only tests for provisional severity rules and review flags."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.src.severity_assessment import (  # noqa: E402
    AssessmentConfig,
    assess_detection,
    build_assessment_report,
)


def make_detection(class_name="dent", **overrides):
    detection = {
        "detection_id": 0,
        "class_id": 0,
        "class_name": class_name,
        "confidence": 0.9,
        "bbox_xyxy": [10, 10, 30, 30],
        "masks_available": True,
        "mask_area_pixels": 10,
        "mask_area_percent": 0.1,
        "polygons_xy": [[[10, 10], [20, 10], [20, 20], [10, 20]]],
    }
    detection.update(overrides)
    return detection


class TestSeverityLabels(unittest.TestCase):
    def test_minor_moderate_major_and_undetermined_labels(self):
        minor = assess_detection(make_detection("dent"), 100, 100)
        moderate = assess_detection(make_detection("crack"), 100, 100)
        major = assess_detection(make_detection("tire_flat"), 100, 100)
        unknown = assess_detection(make_detection("unknown_damage"), 100, 100)

        self.assertEqual(minor["preliminary_severity"], "minor")
        self.assertEqual(moderate["preliminary_severity"], "moderate")
        self.assertEqual(major["preliminary_severity"], "major")
        self.assertEqual(unknown["preliminary_severity"], "undetermined")
        self.assertTrue(all(item["severity_reasons"] for item in (minor, moderate, major, unknown)))

    def test_image_scale_mask_cue_is_explicit_and_configurable(self):
        detection = make_detection("scratch", mask_area_pixels=600)
        config = AssessmentConfig(major_image_area_percent=5.0)
        assessed = assess_detection(detection, 100, 100, config)
        self.assertEqual(assessed["preliminary_severity"], "major")
        self.assertAlmostEqual(assessed["image_level_mask_area_percent"], 6.0)
        self.assertIsNone(assessed["component_relative_damage_percent"])
        self.assertTrue(any("not a vehicle-component" in r for r in assessed["severity_reasons"]))


class TestUncertaintyAndMasks(unittest.TestCase):
    def test_low_confidence_is_undetermined_and_requires_review(self):
        assessed = assess_detection(make_detection("dent", confidence=0.2), 100, 100)
        self.assertEqual(assessed["preliminary_severity"], "undetermined")
        self.assertTrue(assessed["human_review_required"])
        self.assertTrue(any("Low-confidence" in r for r in assessed["human_review_reasons"]))

    def test_missing_mask_keeps_class_rule_but_requires_review(self):
        assessed = assess_detection(
            make_detection("dent", masks_available=False, mask_area_pixels=0), 100, 100
        )
        self.assertEqual(assessed["preliminary_severity"], "minor")
        self.assertTrue(assessed["human_review_required"])
        self.assertTrue(any("No segmentation mask" in r for r in assessed["human_review_reasons"]))

    def test_zero_area_available_mask_is_undetermined(self):
        assessed = assess_detection(make_detection("scratch", mask_area_pixels=0), 100, 100)
        self.assertEqual(assessed["preliminary_severity"], "undetermined")
        self.assertTrue(assessed["human_review_required"])
        self.assertTrue(any("zero" in r.lower() for r in assessed["human_review_reasons"]))

    def test_crack_scale_flag_requests_inspection(self):
        assessed = assess_detection(make_detection("crack", mask_area_pixels=200), 100, 100)
        self.assertIn(
            "potentially_significant_crack",
            [flag["flag"] for flag in assessed["inspection_flags"]],
        )
        self.assertTrue(assessed["human_review_required"])


class TestSafetyAndReport(unittest.TestCase):
    def test_safety_relevant_classes_flag_review_without_driving_claim(self):
        for class_name in ("glass_shatter", "lamp_broken", "tire_flat"):
            with self.subTest(class_name=class_name):
                assessed = assess_detection(make_detection(class_name), 100, 100)
                self.assertTrue(assessed["human_review_required"])
                self.assertIn(
                    "safety_relevant_inspection",
                    [flag["flag"] for flag in assessed["inspection_flags"]],
                )
                self.assertTrue(any("safe to drive" in r for r in assessed["human_review_reasons"]))

    def test_empty_detection_list_has_zero_counts_for_all_labels(self):
        report = build_assessment_report({
            "image_path": "empty.jpg", "image_width": 640, "image_height": 480,
            "detections": [],
        })
        self.assertEqual(report["summary"]["detection_count"], 0)
        self.assertEqual(report["summary"]["human_review_count"], 0)
        self.assertEqual(
            report["summary"]["counts_by_severity"],
            {"minor": 0, "moderate": 0, "major": 0, "undetermined": 0},
        )
        self.assertIn("not a professional inspection", report["disclaimer"])

    def test_bbox_overlap_in_legacy_report_requires_review(self):
        first = make_detection("dent", detection_id=10)
        second = make_detection(
            "scratch", detection_id=11, bbox_xyxy=[15, 15, 35, 35]
        )
        report = build_assessment_report({
            "image_path": "overlap.jpg", "image_width": 100, "image_height": 100,
            "detections": [first, second],
        })
        self.assertEqual(len(report["overlap_pairs"]), 1)
        self.assertTrue(report["overlap_pairs"][0]["human_review_required"])
        self.assertTrue(all(d["human_review_required"] for d in report["detections"]))


if __name__ == "__main__":
    unittest.main()
