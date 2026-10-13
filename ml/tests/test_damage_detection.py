"""CPU-only unit tests for damage_detection helpers. No GPU / weights needed."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.src.damage_detection import (  # noqa: E402
    COORDINATE_SYSTEM,
    bbox_iou,
    clip_bbox_to_image,
    diagnose_overlaps,
    empty_result,
    format_detection,
    mask_area_from_polygons,
    polygon_area,
)


def write_test_image(path: Path) -> Path:
    import cv2
    import numpy as np

    image = np.full((64, 96, 3), 180, dtype=np.uint8)
    if not cv2.imwrite(str(path), image):
        raise OSError("Could not create temporary test image")
    return path


class TestCoordinates(unittest.TestCase):
    def test_coordinate_system_documented(self):
        self.assertIn("original-image", COORDINATE_SYSTEM)
        self.assertIn("top-left", COORDINATE_SYSTEM)

    def test_clip_bbox_inside_unchanged(self):
        self.assertEqual(
            clip_bbox_to_image([10.0, 20.0, 30.0, 40.0], 100, 100),
            [10.0, 20.0, 30.0, 40.0],
        )

    def test_clip_bbox_clamps_to_frame(self):
        self.assertEqual(
            clip_bbox_to_image([-5.0, -5.0, 150.0, 200.0], 100, 80),
            [0.0, 0.0, 100.0, 80.0],
        )


class TestPolygons(unittest.TestCase):
    def test_polygon_area_square(self):
        square = [[0, 0], [10, 0], [10, 10], [0, 10]]
        self.assertAlmostEqual(polygon_area(square), 100.0)

    def test_polygon_area_degenerate(self):
        self.assertEqual(polygon_area([[0, 0], [1, 1]]), 0.0)

    def test_mask_area_from_square(self):
        square = [[[10, 10], [20, 10], [20, 20], [10, 20]]]
        area = mask_area_from_polygons(square, 100, 100)
        self.assertGreater(area, 0)
        self.assertLessEqual(area, 121 + 20)  # rasterized ~10x10 px square
        self.assertEqual(mask_area_from_polygons([], 100, 100), 0)

    def test_mask_area_is_rasterized_pixel_count(self):
        square = [[[10, 10], [20, 10], [20, 20], [10, 20]]]
        self.assertEqual(mask_area_from_polygons(square, 100, 100), 121)
        self.assertEqual(mask_area_from_polygons(square, 0, 100), 0)


class TestFormatting(unittest.TestCase):
    def test_empty_result(self):
        res = empty_result("some.jpg", 640, 480, "m.pt", "cpu")
        self.assertEqual(res["detection_count"], 0)
        self.assertEqual(res["detections"], [])
        self.assertFalse(res["masks_available"])
        self.assertEqual(res["image_width"], 640)
        self.assertEqual(res["image_height"], 480)

    def test_format_detection_keeps_orig_pixel_coords(self):
        poly = [[[10, 10], [20, 10], [20, 20], [10, 20]]][0]
        det = format_detection(
            0, 2, "crack", 0.9, [10.0, 10.0, 20.0, 20.0], [poly], 100, 100
        )
        self.assertEqual(det["class_id"], 2)
        self.assertEqual(det["class_name"], "crack")
        self.assertAlmostEqual(det["confidence"], 0.9)
        self.assertEqual(det["bbox_xyxy"], [10.0, 10.0, 20.0, 20.0])
        self.assertTrue(det["masks_available"])
        self.assertGreater(det["mask_area_pixels"], 0)
        self.assertGreater(det["mask_area_percent"], 0.0)
        self.assertLess(det["mask_area_percent"], 100.0)
        self.assertEqual(det["mask_area_scope"], "whole_image")
        self.assertEqual(det["mask_area_percent_of_image"], det["mask_area_percent"])
        self.assertFalse(det["component_relative_area_available"])
        self.assertIsNone(det["component_relative_area_percent"])

    def test_format_detection_without_mask(self):
        det = format_detection(1, 0, "dent", 0.5, [0, 0, 5, 5], [], 100, 100)
        self.assertFalse(det["masks_available"])
        self.assertEqual(det["mask_area_pixels"], 0)
        self.assertEqual(det["mask_area_percent"], 0.0)


class TestAnalyzeImageErrors(unittest.TestCase):
    def test_missing_file_raises_without_loading_model(self):
        from ml.src import damage_detection

        with self.assertRaises(FileNotFoundError):
            damage_detection.analyze_image(
                "does/not/exist.jpg", model_path="does/not/exist.pt"
            )

    def test_empty_detections_with_fake_model(self):
        from ml.src import damage_detection

        class FakeBoxes:
            def __len__(self):
                return 0

        class FakeResult:
            boxes = FakeBoxes()
            masks = None

        class FakeModel:
            names = {0: "dent"}

            def predict(self, **kwargs):
                return [FakeResult()]

        with tempfile.TemporaryDirectory() as temp_dir:
            img_path = write_test_image(Path(temp_dir) / "test.png")
            res = damage_detection.analyze_image(str(img_path), model=FakeModel())
            self.assertEqual(res["detection_count"], 0)
            self.assertEqual(res["detections"], [])
            self.assertGreater(res["image_width"], 0)
            self.assertEqual(res["overlap_diagnostics"]["overlapping_pairs"], [])

    def test_valid_detection_extraction_with_fake_model(self):
        from ml.src import damage_detection

        class Scalar:
            def __init__(self, value):
                self.value = value

            def item(self):
                return self.value

        class FakeBox:
            class Coordinates:
                def tolist(self):
                    return [10.0, 20.0, 40.0, 50.0]

            xyxy = [Coordinates()]
            conf = [Scalar(0.875)]
            cls = [Scalar(1)]

        class FakeBoxes(list):
            pass

        class FakeResult:
            boxes = FakeBoxes([FakeBox()])
            masks = type("FakeMasks", (), {
                "xy": [[[12, 22], [32, 22], [32, 42], [12, 42]]]
            })()

        class FakeModel:
            names = {1: "scratch"}

            def predict(self, **kwargs):
                return [FakeResult()]

        with tempfile.TemporaryDirectory() as temp_dir:
            img_path = write_test_image(Path(temp_dir) / "test.png")
            res = damage_detection.analyze_image(str(img_path), model=FakeModel())
            self.assertEqual(res["detection_count"], 1)
            det = res["detections"][0]
            self.assertEqual(det["class_name"], "scratch")
            self.assertAlmostEqual(det["confidence"], 0.875)
            self.assertEqual(det["bbox_xyxy"], [10.0, 20.0, 40.0, 50.0])
            self.assertTrue(det["masks_available"])
            self.assertGreater(det["mask_area_pixels"], 0)


class TestOverlapDiagnostics(unittest.TestCase):
    def test_bbox_iou(self):
        self.assertAlmostEqual(
            bbox_iou([0, 0, 10, 10], [5, 0, 15, 10]), 1 / 3
        )
        self.assertEqual(bbox_iou([0, 0, 1, 1], [2, 2, 3, 3]), 0.0)

    def test_same_class_overlaps_flagged_without_removal(self):
        polygon_a = [[0, 0], [10, 0], [10, 10], [0, 10]]
        polygon_b = [[1, 1], [9, 1], [9, 9], [1, 9]]
        detections = [
            {
                "detection_id": 0, "class_id": 2,
                "bbox_xyxy": [0, 0, 10, 10], "polygons_xy": [polygon_a],
            },
            {
                "detection_id": 1, "class_id": 2,
                "bbox_xyxy": [1, 1, 9, 9], "polygons_xy": [polygon_b],
            },
        ]
        report = diagnose_overlaps(detections, 20, 20)
        self.assertEqual(len(detections), 2)
        self.assertEqual(len(report["overlapping_pairs"]), 1)
        pair = report["overlapping_pairs"][0]
        self.assertGreater(pair["bbox_iou"], 0.5)
        self.assertGreater(pair["mask_iou"], 0.5)
        self.assertTrue(pair["possible_duplicate_for_review"])
        self.assertEqual(report["possible_duplicate_pair_count"], 1)

    def test_different_classes_reported_but_not_flagged_duplicate(self):
        detections = [
            {"detection_id": 0, "class_id": 0, "bbox_xyxy": [0, 0, 10, 10]},
            {"detection_id": 1, "class_id": 1, "bbox_xyxy": [1, 1, 9, 9]},
        ]
        report = diagnose_overlaps(detections, 20, 20)
        pair = report["overlapping_pairs"][0]
        self.assertFalse(pair["same_class"])
        self.assertFalse(pair["possible_duplicate_for_review"])
        self.assertIsNone(pair["mask_iou"])


if __name__ == "__main__":
    unittest.main()
