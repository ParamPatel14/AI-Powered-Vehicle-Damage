"""Reusable primary damage detection service (YOLOv8s-seg, inference only).

Primary checkpoint: ml/weights/cardd-yolov8s-v2.pt

Coordinate system (documented contract):
- All ``bbox_xyxy`` values are [x1, y1, x2, y2] floats in ORIGINAL-IMAGE
  pixel coordinates: origin at the top-left, x increases right, y increases
  down (same indexing as cv2 / PIL).
- All ``polygons_xy`` entries are lists of [x, y] points in the SAME
  original-image pixel coordinate system (taken from Ultralytics
  ``result.masks.xy``, which is already rescaled to the original image).
- ``mask_area_pixels`` is the rasterized polygon pixel count on a
  width x height canvas matching the original image; ``mask_area_percent``
  is that count divided by (width * height) * 100. This is image-level area,
  not area relative to a vehicle component; no component segmentation exists.

No severity classification, no repair-cost estimation, no ensemble.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

DEFAULT_MODEL = Path("ml/weights/cardd-yolov8s-v2.pt")
DEFAULT_OUTPUT_DIR = Path("outputs/damage_detection")

COORDINATE_SYSTEM = (
    "original-image pixel coordinates: bbox [x1, y1, x2, y2] and polygon "
    "[x, y] points share the original image frame, origin top-left, "
    "x right, y down (cv2/PIL indexing)"
)

DUPLICATE_REVIEW_IOU_THRESHOLD = 0.5

# Process-wide cache so repeated analyze_image() calls reuse one YOLO object.
_CACHED_MODELS: dict = {}


def get_device() -> str:
    """Use CUDA device 0 when available, otherwise CPU."""
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def get_model(model_path: Path | str = DEFAULT_MODEL) -> YOLO:
    """Load (once) the local checkpoint. Never downloads a model."""
    key = str(model_path)
    if key in _CACHED_MODELS:
        return _CACHED_MODELS[key]
    path = Path(model_path)
    if not path.is_file():
        # Check first so Ultralytics does not attempt a Hub download.
        raise FileNotFoundError(f"Model weights not found: {path}")
    try:
        model = YOLO(str(path))
    except Exception as exc:
        raise RuntimeError(f"Failed to load YOLO checkpoint {path}: {exc}") from exc
    _CACHED_MODELS[key] = model
    return model


# ---------------------------------------------------------------------------
# Pure helpers (CPU-only, unit-testable without GPU / weights).
# ---------------------------------------------------------------------------

def clip_bbox_to_image(bbox_xyxy, width: int, height: int) -> list:
    """Clip [x1, y1, x2, y2] into the original-image frame."""
    x1, y1, x2, y2 = (float(v) for v in bbox_xyxy)
    x1 = min(max(x1, 0.0), float(width))
    y1 = min(max(y1, 0.0), float(height))
    x2 = min(max(x2, 0.0), float(width))
    y2 = min(max(y2, 0.0), float(height))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return [x1, y1, x2, y2]


def polygon_area(polygon_xy) -> float:
    """Shoelace area of one polygon in original-image pixel coordinates."""
    pts = np.asarray(polygon_xy, dtype=float)
    if pts.shape[0] < 3:
        return 0.0
    x, y = pts[:, 0], pts[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def mask_area_from_polygons(polygons_xy, width: int, height: int) -> int:
    """Rasterize polygons onto a WxH canvas and count mask pixels."""
    if not polygons_xy or width <= 0 or height <= 0:
        return 0
    canvas = np.zeros((height, width), dtype=np.uint8)
    polys = []
    for poly in polygons_xy:
        arr = np.asarray(poly, dtype=np.int32)
        if arr.shape[0] >= 3:
            polys.append(arr.reshape(-1, 1, 2))
    if not polys:
        return 0
    cv2.fillPoly(canvas, polys, 1)
    return int(np.count_nonzero(canvas))


def bbox_iou(bbox_a, bbox_b) -> float:
    """Intersection over union for two [x1, y1, x2, y2] boxes."""
    ax1, ay1, ax2, ay2 = (float(v) for v in bbox_a)
    bx1, by1, bx2, by2 = (float(v) for v in bbox_b)
    intersection_width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    intersection_height = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = intersection_width * intersection_height
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return float(intersection / union) if union > 0 else 0.0


def mask_iou(polygons_a, polygons_b, width: int, height: int):
    """Raster mask IoU, or None if either detection has no usable mask."""
    if not polygons_a or not polygons_b or width <= 0 or height <= 0:
        return None
    mask_a = np.zeros((height, width), dtype=np.uint8)
    mask_b = np.zeros((height, width), dtype=np.uint8)
    for canvas, polygons in ((mask_a, polygons_a), (mask_b, polygons_b)):
        valid = []
        for polygon in polygons:
            points = np.asarray(polygon, dtype=np.int32)
            if points.ndim == 2 and points.shape[0] >= 3:
                valid.append(points.reshape(-1, 1, 2))
        if valid:
            cv2.fillPoly(canvas, valid, 1)
    intersection = int(np.count_nonzero((mask_a != 0) & (mask_b != 0)))
    union = int(np.count_nonzero((mask_a != 0) | (mask_b != 0)))
    return float(intersection / union) if union else 0.0


def diagnose_overlaps(
    detections: list,
    image_width: int,
    image_height: int,
    review_iou_threshold: float = DUPLICATE_REVIEW_IOU_THRESHOLD,
) -> dict:
    """Report pairwise overlap and flag same-class candidates for review."""
    overlaps = []
    for left_index in range(len(detections)):
        left = detections[left_index]
        for right_index in range(left_index + 1, len(detections)):
            right = detections[right_index]
            box_overlap = bbox_iou(left["bbox_xyxy"], right["bbox_xyxy"])
            masks_overlap = mask_iou(
                left.get("polygons_xy", []),
                right.get("polygons_xy", []),
                image_width,
                image_height,
            )
            if box_overlap <= 0 and (masks_overlap is None or masks_overlap <= 0):
                continue
            same_class = left.get("class_id") == right.get("class_id")
            comparable_ious = [box_overlap]
            if masks_overlap is not None:
                comparable_ious.append(masks_overlap)
            possible_duplicate = same_class and max(comparable_ious) >= review_iou_threshold
            overlaps.append({
                "detection_ids": [left["detection_id"], right["detection_id"]],
                "bbox_iou": box_overlap,
                "mask_iou": masks_overlap,
                "same_class": same_class,
                "possible_duplicate_for_review": possible_duplicate,
                "review_reason": (
                    "same-class overlap meets review threshold"
                    if possible_duplicate
                    else None
                ),
            })
    return {
        "method": "pairwise IoU; detections are retained unchanged",
        "duplicate_review_iou_threshold": float(review_iou_threshold),
        "overlapping_pairs": overlaps,
        "possible_duplicate_pair_count": sum(
            pair["possible_duplicate_for_review"] for pair in overlaps
        ),
    }


def format_detection(
    detection_id: int,
    class_id: int,
    class_name: str,
    confidence: float,
    bbox_xyxy,
    polygons_xy: list,
    image_width: int,
    image_height: int,
) -> dict:
    """Build one structured detection dict (pure, testable)."""
    bbox = clip_bbox_to_image(bbox_xyxy, image_width, image_height)
    clean_polys = []
    for poly in polygons_xy or []:
        arr = np.asarray(poly, dtype=float).tolist()
        if len(arr) >= 3:
            clean_polys.append([[float(x), float(y)] for x, y in arr])
    area = mask_area_from_polygons(clean_polys, image_width, image_height)
    total = image_width * image_height
    percent = (area / total * 100.0) if total > 0 else 0.0
    return {
        "detection_id": int(detection_id),
        "class_id": int(class_id),
        "class_name": str(class_name),
        "confidence": float(confidence),
        "bbox_xyxy": bbox,
        "masks_available": bool(clean_polys),
        "mask_area_pixels": area,
        "mask_area_percent": float(percent),
        "mask_area_scope": "whole_image",
        "mask_area_percent_of_image": float(percent),
        "component_relative_area_percent": None,
        "component_relative_area_available": False,
        "polygons_xy": clean_polys,
    }


def empty_result(
    image_path: Path | str,
    image_width: int = 0,
    image_height: int = 0,
    model_name: str = "",
    device: str = "",
    confidence_threshold: float = 0.25,
    image_size: int = 640,
) -> dict:
    """Structured result for images with no detections (pure, testable)."""
    return {
        "image_path": str(image_path),
        "image_width": int(image_width),
        "image_height": int(image_height),
        "model_name": model_name,
        "inference_device": device,
        "image_size": int(image_size),
        "confidence_threshold": float(confidence_threshold),
        "coordinate_system": COORDINATE_SYSTEM,
        "detection_count": 0,
        "detections": [],
        "masks_available": False,
        "overlap_diagnostics": diagnose_overlaps([], image_width, image_height),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Service API.
# ---------------------------------------------------------------------------

def analyze_image(
    image_path: Path | str,
    confidence_threshold: float = 0.25,
    image_size: int = 640,
    model_path: Path | str = DEFAULT_MODEL,
    model=None,
) -> dict:
    """Run primary damage detection on one image; return structured results.

    Bboxes and polygons are in original-image pixel coordinates (see
    COORDINATE_SYSTEM). Raises FileNotFoundError (missing file),
    ValueError (unsupported/unreadable image), RuntimeError (inference failure).
    Images with no detections return a valid result with detections == [].
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {path}")

    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Unsupported or unreadable image: {path}")
    height, width = image.shape[:2]

    active_model = model if model is not None else get_model(model_path)
    device = get_device()
    names = getattr(active_model, "names", {})
    model_name = Path(model_path).name

    try:
        results = active_model.predict(
            source=str(path),
            imgsz=image_size,
            conf=confidence_threshold,
            device=device,
            verbose=False,
        )
    except Exception as exc:
        raise RuntimeError(f"Inference failed for {path}: {exc}") from exc

    if not results:
        return empty_result(path, width, height, model_name, device,
                            confidence_threshold, image_size)

    result = results[0]
    boxes = getattr(result, "boxes", None)
    masks = getattr(result, "masks", None)
    polygons_all: list = []
    if masks is not None and getattr(masks, "xy", None) is not None:
        try:
            polygons_all = [np.asarray(p, dtype=float) for p in masks.xy]
        except Exception:
            polygons_all = []

    detections = []
    if boxes is not None and len(boxes) > 0:
        for i, box in enumerate(boxes):
            bbox = [float(v) for v in box.xyxy[0].tolist()]
            conf = float(box.conf[0].item())
            cls_id = int(box.cls[0].item())
            cls_name = str(names.get(cls_id, cls_id)) if isinstance(names, dict) else str(cls_id)
            polys = [polygons_all[i].tolist()] if i < len(polygons_all) and len(polygons_all[i]) >= 3 else []
            detections.append(
                format_detection(i, cls_id, cls_name, conf, bbox, polys, width, height)
            )

    return {
        "image_path": str(path),
        "image_width": int(width),
        "image_height": int(height),
        "model_name": model_name,
        "model_path": str(model_path),
        "inference_device": device,
        "image_size": int(image_size),
        "confidence_threshold": float(confidence_threshold),
        "coordinate_system": COORDINATE_SYSTEM,
        "detection_count": len(detections),
        "detections": detections,
        "masks_available": any(d["masks_available"] for d in detections),
        "overlap_diagnostics": diagnose_overlaps(detections, width, height),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


def create_annotated_preview(
    image_path: Path | str,
    result: dict,
    output_path: Path | str,
) -> Path:
    """Draw boxes, labels, scores and masks; save preview. Returns output path."""
    src = Path(image_path)
    image = cv2.imread(str(src))
    if image is None:
        raise FileNotFoundError(f"Cannot read image for preview: {src}")
    if not isinstance(result, dict) or "detections" not in result:
        raise ValueError("Invalid result dict: missing 'detections'.")

    overlay = image.copy()
    for det in result.get("detections", []):
        for poly in det.get("polygons_xy", []):
            pts = np.asarray(poly, dtype=np.int32).reshape(-1, 1, 2)
            if len(pts) >= 3:
                cv2.fillPoly(overlay, [pts], (0, 255, 0))
    preview = cv2.addWeighted(overlay, 0.35, image, 0.65, 0)

    for det in result.get("detections", []):
        x1, y1, x2, y2 = (int(round(v)) for v in det["bbox_xyxy"])
        label = f"{det['class_name']} {det['confidence']:.2f}"
        cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 0, 255), 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(preview, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), (0, 0, 255), -1)
        cv2.putText(preview, label, (x1 + 3, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), preview):
        raise OSError(f"Failed to write preview: {out}")
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Primary damage detection CLI (inference only; no severity/cost)."
    )
    parser.add_argument("images", nargs="+", help="Input image(s) to analyze.")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        model = get_model(args.model)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    failures = 0
    for image_str in args.images:
        stem = Path(image_str).stem
        json_path = out_dir / f"{stem}_result.json"
        preview_path = out_dir / f"{stem}_annotated.jpg"
        try:
            result = analyze_image(
                image_str,
                confidence_threshold=args.conf,
                image_size=args.imgsz,
                model_path=args.model,
                model=model,  # reuse: no reload per image
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            print(f"Error [{image_str}]: {exc}", file=sys.stderr)
            failures += 1
            continue

        try:
            json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            create_annotated_preview(image_str, result, preview_path)
        except (OSError, ValueError) as exc:
            print(f"Error [{image_str}]: cannot save outputs: {exc}", file=sys.stderr)
            failures += 1
            continue

        if result["detection_count"] == 0:
            print(f"{image_str}: no damage detected.")
        else:
            for det in result["detections"]:
                print(
                    f"{image_str}: {det['class_name']} conf={det['confidence']:.4f} "
                    f"bbox={det['bbox_xyxy']} mask={det['masks_available']} "
                    f"area={det['mask_area_pixels']}px ({det['mask_area_percent']:.2f}%)"
                )
        duplicate_count = result["overlap_diagnostics"]["possible_duplicate_pair_count"]
        if duplicate_count:
            print(
                f"{image_str}: {duplicate_count} possible duplicate pair(s) "
                "flagged for review; detections retained."
            )
        print(f"Saved JSON: {json_path}")
        print(f"Saved preview: {preview_path}")

    if failures:
        print(f"Completed with {failures} failure(s).", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
