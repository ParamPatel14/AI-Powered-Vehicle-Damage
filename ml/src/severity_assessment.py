"""Explainable, provisional severity assessment for CarDD detector JSON.

This module does not change detections. Its rules are initial heuristics only;
they are not validated severity criteria and require calibration with labeled
examples and expert review. Mask footprint is measured against the whole image
when dimensions are available, never against an assumed vehicle component.
"""

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


DEFAULT_OUTPUT_DIR = Path("outputs/severity_assessment")
SEVERITY_LABELS = ("minor", "moderate", "major", "undetermined")
SAFETY_RELEVANT_CLASSES = frozenset(
    {"glass_shatter", "lamp_broken", "tire_flat"}
)


@dataclass(frozen=True)
class AssessmentConfig:
    """Configurable starting points, not scientifically validated thresholds."""

    # These use whole-image mask footprint as a rough visible-scale cue only.
    moderate_image_area_percent: float = 1.0
    major_image_area_percent: float = 5.0
    significant_crack_image_area_percent: float = 1.5
    minimum_assessment_confidence: float = 0.35
    human_review_confidence: float = 0.60
    overlap_review_iou: float = 0.0
    class_base_severity: Mapping[str, str] = field(default_factory=lambda: {
        "dent": "minor",
        "scratch": "minor",
        "crack": "moderate",
        "glass_shatter": "moderate",
        "lamp_broken": "moderate",
        "tire_flat": "major",
    })

    def __post_init__(self):
        if self.moderate_image_area_percent < 0:
            raise ValueError("moderate_image_area_percent must be non-negative")
        if self.major_image_area_percent < self.moderate_image_area_percent:
            raise ValueError("major area threshold must be >= moderate threshold")
        if self.significant_crack_image_area_percent < 0:
            raise ValueError("significant crack threshold must be non-negative")
        for name in ("minimum_assessment_confidence", "human_review_confidence", "overlap_review_iou"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.minimum_assessment_confidence > self.human_review_confidence:
            raise ValueError(
                "minimum assessment confidence must be <= human review confidence"
            )
        invalid = {
            label for label in self.class_base_severity.values()
            if label not in SEVERITY_LABELS
        }
        if invalid:
            raise ValueError(f"invalid class severity label(s): {sorted(invalid)}")


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _bbox_iou(box_a, box_b) -> float:
    """IoU for xyxy boxes; malformed or absent boxes produce zero."""
    try:
        ax1, ay1, ax2, ay2 = map(float, box_a)
        bx1, by1, bx2, by2 = map(float, box_b)
    except (TypeError, ValueError):
        return 0.0
    if not all(map(math.isfinite, (ax1, ay1, ax2, ay2, bx1, by1, bx2, by2))):
        return 0.0
    intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(
        0.0, min(ay2, by2) - max(ay1, by1)
    )
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _overlap_pairs(detector_result: dict, detections: list, config: AssessmentConfig):
    """Use detector diagnostics when available and derive box IoU for old JSON."""
    found = {}
    source_diagnostics = detector_result.get("overlap_diagnostics") or {}
    for pair in source_diagnostics.get("overlapping_pairs", []):
        ids = pair.get("detection_ids", [])
        if len(ids) != 2:
            continue
        key = frozenset(ids)
        found[key] = {
            "detection_ids": list(ids),
            "bbox_iou": _finite_number(pair.get("bbox_iou")),
            "mask_iou": _finite_number(pair.get("mask_iou")),
            "possible_duplicate_for_review": bool(
                pair.get("possible_duplicate_for_review", False)
            ),
        }

    # Existing saved reports predate overlap_diagnostics, so derive bbox IoU.
    for left_index, left in enumerate(detections):
        for right_index in range(left_index + 1, len(detections)):
            right = detections[right_index]
            left_id = left.get("detection_id", left_index)
            right_id = right.get("detection_id", right_index)
            key = frozenset((left_id, right_id))
            iou = _bbox_iou(left.get("bbox_xyxy"), right.get("bbox_xyxy"))
            if iou > 0:
                current = found.get(key, {"detection_ids": [left_id, right_id]})
                current["bbox_iou"] = iou
                current.setdefault("mask_iou", None)
                current.setdefault("possible_duplicate_for_review", False)
                found[key] = current

    id_to_reasons = {}
    report_pairs = []
    for pair in found.values():
        bbox_iou = pair.get("bbox_iou") or 0.0
        mask_iou = pair.get("mask_iou")
        should_review = (
            pair.get("possible_duplicate_for_review", False)
            or bbox_iou > config.overlap_review_iou
            or (mask_iou is not None and mask_iou > 0)
        )
        if should_review:
            reason = (
                "This detection overlaps another detection; verify that both "
                "findings are distinct. No detection was removed or merged."
            )
            for detection_id in pair["detection_ids"]:
                id_to_reasons.setdefault(detection_id, []).append(reason)
        report_pairs.append({
            "detection_ids": pair["detection_ids"],
            "bbox_iou": bbox_iou,
            "mask_iou": mask_iou,
            "human_review_required": should_review,
        })
    return report_pairs, id_to_reasons


def _image_area_percent(detection: dict, image_width, image_height):
    """Return image-level mask footprint percent, or None when unavailable."""
    area_pixels = _finite_number(detection.get("mask_area_pixels"))
    width = _finite_number(image_width)
    height = _finite_number(image_height)
    if area_pixels is not None and width and height and width > 0 and height > 0:
        return max(0.0, area_pixels) / (width * height) * 100.0

    # Legacy detector reports document mask_area_percent as whole-image area.
    if detection.get("mask_area_scope", "whole_image") == "whole_image":
        percent = _finite_number(
            detection.get("mask_area_percent_of_image", detection.get("mask_area_percent"))
        )
        if percent is not None and percent >= 0:
            return percent
    return None


def assess_detection(
    detection: dict,
    image_width,
    image_height,
    config: AssessmentConfig | None = None,
) -> dict:
    """Assess one detector record and preserve it verbatim as original evidence."""
    config = config or AssessmentConfig()
    class_name = str(detection.get("class_name", "")).strip().lower()
    confidence = _finite_number(detection.get("confidence"))
    masks_available = detection.get("masks_available") is True
    mask_area_pixels = _finite_number(detection.get("mask_area_pixels"))
    image_percent = _image_area_percent(detection, image_width, image_height)

    reasons = []
    inspection_flags = []
    review_reasons = [
        "Preliminary severity uses unvalidated rules and must be confirmed by a human reviewer."
    ]
    base = config.class_base_severity.get(class_name)

    if base is None:
        severity = "undetermined"
        reasons.append(f"Unknown damage class {class_name!r}; no provisional class rule applies.")
        review_reasons.append("Unknown damage class requires human interpretation.")
    elif confidence is None:
        severity = "undetermined"
        reasons.append("Confidence is missing or invalid, so the assessment is undetermined.")
        review_reasons.append("Detection confidence is unavailable or invalid.")
    elif confidence < config.minimum_assessment_confidence:
        severity = "undetermined"
        reasons.append(
            f"Confidence {confidence:.3f} is below the provisional minimum "
            f"{config.minimum_assessment_confidence:.3f}; severity is undetermined."
        )
        review_reasons.append("Low-confidence detection requires visual confirmation.")
    elif masks_available and mask_area_pixels is not None and mask_area_pixels <= 0:
        severity = "undetermined"
        reasons.append("A mask is marked available but its measured pixel area is zero.")
        review_reasons.append("Zero-area mask provides no usable extent evidence.")
    else:
        severity = base
        reasons.append(
            f"Provisional class rule for {class_name!r} starts at {base!r}; "
            "confidence is treated as detection certainty, not severity."
        )
        if image_percent is not None:
            if image_percent >= config.major_image_area_percent:
                severity = "major"
                reasons.append(
                    f"Image-level mask footprint {image_percent:.2f}% meets the "
                    f"provisional major scale cue ({config.major_image_area_percent:.2f}%). "
                    "This is not a vehicle-component damage percentage."
                )
            elif image_percent >= config.moderate_image_area_percent:
                if severity == "minor":
                    severity = "moderate"
                reasons.append(
                    f"Image-level mask footprint {image_percent:.2f}% meets the "
                    f"provisional moderate scale cue ({config.moderate_image_area_percent:.2f}%). "
                    "This is not a vehicle-component damage percentage."
                )
        else:
            reasons.append("Mask scale could not be assessed from available mask area and image dimensions.")
            review_reasons.append("Mask extent evidence is unavailable or incomplete.")

    if confidence is not None and confidence < config.human_review_confidence:
        review_reasons.append(
            f"Confidence {confidence:.3f} is below the provisional human-review "
            f"threshold {config.human_review_confidence:.3f}."
        )
    if class_name in SAFETY_RELEVANT_CLASSES:
        flag_reason = (
            f"{class_name} is a safety-relevant visual finding that warrants closer "
            "inspection; this image does not establish whether the vehicle is safe to drive."
        )
        inspection_flags.append({"flag": "safety_relevant_inspection", "reason": flag_reason})
        review_reasons.append(flag_reason)
    if class_name == "crack":
        if image_percent is not None and image_percent >= config.significant_crack_image_area_percent:
            flag_reason = (
                f"Crack mask footprint reaches the provisional image-scale inspection "
                f"cue ({config.significant_crack_image_area_percent:.2f}% of the whole image)."
            )
            inspection_flags.append({"flag": "potentially_significant_crack", "reason": flag_reason})
            review_reasons.append(flag_reason)
        elif image_percent is None:
            flag_reason = "Crack extent is unavailable; inspect to determine its significance."
            inspection_flags.append({"flag": "crack_extent_unassessed", "reason": flag_reason})
            review_reasons.append(flag_reason)

    if not masks_available:
        review_reasons.append("No segmentation mask is available to assess visible extent.")

    return {
        "original_evidence": detection,
        "preliminary_severity": severity,
        "severity_reasons": reasons,
        "image_level_mask_area_percent": image_percent,
        "mask_area_scope": "whole_image; not relative to a vehicle component",
        "component_relative_damage_percent": None,
        "inspection_flags": inspection_flags,
        "human_review_required": bool(review_reasons),
        "human_review_reasons": list(dict.fromkeys(review_reasons)),
    }


def build_assessment_report(
    detector_result: dict,
    source_detection_file: str | Path | None = None,
    config: AssessmentConfig | None = None,
) -> dict:
    """Create an explainable preliminary report from one detector JSON object."""
    config = config or AssessmentConfig()
    if not isinstance(detector_result, dict):
        raise ValueError("Detection result must be a JSON object.")
    detections = detector_result.get("detections")
    if not isinstance(detections, list):
        raise ValueError("Detection result must contain a 'detections' list.")
    width = detector_result.get("image_width")
    height = detector_result.get("image_height")
    overlap_pairs, overlap_review = _overlap_pairs(detector_result, detections, config)

    assessed = []
    for index, detection in enumerate(detections):
        if not isinstance(detection, dict):
            raise ValueError(f"Detection at index {index} must be a JSON object.")
        item = assess_detection(detection, width, height, config)
        detection_id = detection.get("detection_id", index)
        overlap_reasons = overlap_review.get(detection_id, [])
        if overlap_reasons:
            item["human_review_reasons"] = list(dict.fromkeys(
                item["human_review_reasons"] + overlap_reasons
            ))
            item["human_review_required"] = True
        assessed.append(item)

    counts = {label: 0 for label in SEVERITY_LABELS}
    for item in assessed:
        counts[item["preliminary_severity"]] += 1

    rules = asdict(config)
    rules["class_base_severity"] = dict(config.class_base_severity)
    return {
        "report_type": "preliminary_image_based_damage_severity_assessment",
        "assessment_status": "provisional; requires human review",
        "source_image": detector_result.get("image_path"),
        "source_detection_file": str(source_detection_file) if source_detection_file else None,
        "source_image_dimensions": {"width": width, "height": height},
        "detections": assessed,
        "overlap_pairs": overlap_pairs,
        "summary": {
            "detection_count": len(assessed),
            "counts_by_severity": counts,
            "human_review_count": sum(item["human_review_required"] for item in assessed),
            "inspection_flag_count": sum(bool(item["inspection_flags"]) for item in assessed),
        },
        "rules": {
            "name": "provisional_class_and_image_scale_heuristics_v1",
            "validated": False,
            "configuration": rules,
            "interpretation": (
                "Rules are initial configurable heuristics, not scientifically validated. "
                "Calibrate with labeled examples and expert review. Whole-image mask area "
                "is only a visible-scale cue and is never a vehicle-panel percentage."
            ),
        },
        "disclaimer": (
            "This is an image-based preliminary assessment, not a professional inspection. "
            "It cannot establish the damaged vehicle component, structural integrity, hidden "
            "damage, repair method, or exact repair cost. Safety-relevant flags request closer "
            "assessment and do not determine whether the vehicle is safe to drive. Human review "
            "is required where flagged."
        ),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


def _read_detection_file(path: Path):
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read detection JSON {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError(f"Detection JSON must contain an object: {path}")
    return result


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create a provisional, explainable severity report from detector JSON."
    )
    parser.add_argument("detection_json", nargs="+", help="Existing detection JSON file(s).")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--moderate-area-percent", type=float, default=1.0,
                        help="Provisional whole-image mask footprint cue for moderate severity.")
    parser.add_argument("--major-area-percent", type=float, default=5.0,
                        help="Provisional whole-image mask footprint cue for major severity.")
    parser.add_argument("--significant-crack-area-percent", type=float, default=1.5)
    parser.add_argument("--minimum-confidence", type=float, default=0.35,
                        help="Below this confidence the preliminary severity is undetermined.")
    parser.add_argument("--review-confidence", type=float, default=0.60)
    parser.add_argument("--overlap-review-iou", type=float, default=0.0,
                        help="BBox IoU above this value requires human review; default flags any overlap.")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        config = AssessmentConfig(
            moderate_image_area_percent=args.moderate_area_percent,
            major_image_area_percent=args.major_area_percent,
            significant_crack_image_area_percent=args.significant_crack_area_percent,
            minimum_assessment_confidence=args.minimum_confidence,
            human_review_confidence=args.review_confidence,
            overlap_review_iou=args.overlap_review_iou,
        )
    except ValueError as exc:
        print(f"Error: invalid assessment configuration: {exc}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Error: cannot create output directory {output_dir}: {exc}", file=sys.stderr)
        return 1

    failures = 0
    for input_name in args.detection_json:
        input_path = Path(input_name)
        try:
            report = build_assessment_report(
                _read_detection_file(input_path), input_path, config
            )
            output_path = output_dir / f"{input_path.stem}_severity.json"
            output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except (ValueError, OSError) as exc:
            print(f"Error [{input_path}]: {exc}", file=sys.stderr)
            failures += 1
            continue
        print(
            f"{input_path}: {report['summary']['detection_count']} detections assessed; "
            f"human review required for {report['summary']['human_review_count']}."
        )
        print(f"Saved assessment: {output_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
