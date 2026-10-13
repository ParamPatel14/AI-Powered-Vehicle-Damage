"""Compare vehicle-damage predictions from two models (no ground truth).

Reads per-image prediction JSONs produced by run_inference.py for two
model output dirs and reports descriptive agreement only.

No accuracy / precision / recall / mAP is computed: we have no verified
ground-truth annotations for these images.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

DEFAULT_BASELINE_DIR = Path("outputs/baseline")
DEFAULT_CHALLENGER_DIR = Path("outputs/cardd_v2")
DEFAULT_IMAGES = ["car1", "car2", "car3"]
DEFAULT_OUTPUT_CSV = Path("outputs/model_comparison.csv")
DEFAULT_IOU_THRESHOLD = 0.5
DEFAULT_INTRA_IOU_THRESHOLD = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two models' prediction JSONs (descriptive only)."
    )
    parser.add_argument("--baseline-dir", default=str(DEFAULT_BASELINE_DIR))
    parser.add_argument("--challenger-dir", default=str(DEFAULT_CHALLENGER_DIR))
    parser.add_argument(
        "--images",
        nargs="*",
        default=DEFAULT_IMAGES,
        help="Image stems to compare (default: car1 car2 car3).",
    )
    parser.add_argument(
        "--iou-threshold",
        type=float,
        default=DEFAULT_IOU_THRESHOLD,
        help="IoU >= threshold counts as a cross-model spatial match.",
    )
    parser.add_argument(
        "--intra-iou-threshold",
        type=float,
        default=DEFAULT_INTRA_IOU_THRESHOLD,
        help="IoU >= threshold counts as a within-model potential duplicate.",
    )
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    return parser.parse_args()


def find_predictions_json(model_dir: Path, image: str) -> Path:
    """Support both <dir>/<image>/<image>_predictions.json and <dir>/<image>_predictions.json."""
    nested = model_dir / image / f"{image}_predictions.json"
    flat = model_dir / f"{image}_predictions.json"
    if nested.is_file():
        return nested
    return flat  # caller checks existence so error message shows tried path


def load_predictions(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Predictions file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Malformed JSON in {path}: top-level object must be a dict.")
    dets = data.get("detections", [])
    if not isinstance(dets, list):
        raise ValueError(f"Malformed JSON in {path}: 'detections' must be a list.")
    for i, det in enumerate(dets):
        if not isinstance(det, dict):
            raise ValueError(f"Malformed JSON in {path}: detections[{i}] must be a dict.")
        if "bbox_xyxy" not in det or "class_name" not in det or "confidence" not in det:
            raise ValueError(
                f"Malformed JSON in {path}: detections[{i}] missing "
                "bbox_xyxy / class_name / confidence."
            )
        bbox = det["bbox_xyxy"]
        if not (isinstance(bbox, list) and len(bbox) == 4):
            raise ValueError(
                f"Malformed JSON in {path}: detections[{i}].bbox_xyxy must have 4 numbers."
            )
    return data


def bbox_iou(a: list, b: list) -> float:
    ax1, ay1, ax2, ay2 = (float(v) for v in a)
    bx1, by1, bx2, by2 = (float(v) for v in b)
    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter = inter_w * inter_h
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def norm_label(name) -> str:
    return str(name).strip().lower()


def cross_model_matches(dets_a: list, dets_b: list, iou_thr: float) -> dict:
    """Greedy one-to-one matching by descending IoU.

    Class taxonomies are NOT assumed equivalent: spatial matches (IoU)
    are reported separately from class-label matches (exact normalized match).
    """
    pairs = []
    for i, da in enumerate(dets_a):
        for j, db in enumerate(dets_b):
            iou = bbox_iou(da["bbox_xyxy"], db["bbox_xyxy"])
            if iou >= iou_thr:
                pairs.append((iou, i, j))
    pairs.sort(reverse=True)
    used_a, used_b = set(), set()
    spatial = 0
    class_match = 0
    best_iou = 0.0
    details = []
    for iou, i, j in pairs:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        spatial += 1
        best_iou = max(best_iou, iou)
        same = norm_label(dets_a[i]["class_name"]) == norm_label(dets_b[j]["class_name"])
        if same:
            class_match += 1
        details.append(
            {
                "iou": iou,
                "a_index": i,
                "b_index": j,
                "a_class": dets_a[i]["class_name"],
                "b_class": dets_b[j]["class_name"],
                "class_match": same,
            }
        )
    return {
        "spatial_matches": spatial,
        "class_matches": class_match,
        "best_iou": best_iou,
        "details": details,
    }


def intra_model_duplicates(dets: list, iou_thr: float) -> list:
    """Flag box pairs within one model that overlap substantially.

    'Compatible categories' = identical normalized class label. Different
    labels on overlapping boxes are listed but not flagged as duplicates,
    since one model may legitimately predict adjacent damage types.
    """
    flags = []
    for i in range(len(dets)):
        for j in range(i + 1, len(dets)):
            iou = bbox_iou(dets[i]["bbox_xyxy"], dets[j]["bbox_xyxy"])
            if iou < iou_thr:
                continue
            same = norm_label(dets[i]["class_name"]) == norm_label(dets[j]["class_name"])
            flags.append(
                {
                    "index_a": i,
                    "index_b": j,
                    "iou": iou,
                    "class_a": dets[i]["class_name"],
                    "class_b": dets[j]["class_name"],
                    "compatible": same,
                    "potential_duplicate": same,
                }
            )
    return flags


def summarize(data: dict) -> dict:
    dets = data.get("detections", [])
    return {
        "model_name": str(data.get("model_name", "unknown")),
        "device": str(data.get("inference_device", "unknown")),
        "count": len(dets),
        "classes": [str(d.get("class_name", "?")) for d in dets],
        "scores": [float(d.get("confidence", 0.0)) for d in dets],
        "dets": dets,
    }


def main() -> None:
    args = parse_args()
    baseline_dir = Path(args.baseline_dir)
    challenger_dir = Path(args.challenger_dir)
    output_csv = Path(args.output_csv)

    print("Model comparison (descriptive only — no ground truth).")
    print("Accuracy / precision / recall / mAP are NOT computed.\n")

    rows = []
    had_error = False

    for image in args.images:
        base_path = find_predictions_json(baseline_dir, image)
        chal_path = find_predictions_json(challenger_dir, image)
        try:
            base_data = load_predictions(base_path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error [{image} baseline]: {exc}", file=sys.stderr)
            had_error = True
            continue
        try:
            chal_data = load_predictions(chal_path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error [{image} challenger]: {exc}", file=sys.stderr)
            had_error = True
            continue

        base = summarize(base_data)
        chal = summarize(chal_data)

        match = cross_model_matches(base["dets"], chal["dets"], args.iou_threshold)
        base_dup = intra_model_duplicates(base["dets"], args.intra_iou_threshold)
        chal_dup = intra_model_duplicates(chal["dets"], args.intra_iou_threshold)
        base_dup_count = sum(1 for f in base_dup if f["potential_duplicate"])
        chal_dup_count = sum(1 for f in chal_dup if f["potential_duplicate"])

        # --- Console comparison table ---
        print(f"=== {image} ===")
        print(
            f"{'model':<28} {'count':<6} {'device':<8} classes (confidence)"
        )
        for label, s in (("baseline", base), ("challenger", chal)):
            cls_str = (
                ", ".join(f"{c} ({sc:.2f})" for c, sc in zip(s["classes"], s["scores"]))
                or "(no detections)"
            )
            print(f"{s['model_name']:<28} {s['count']:<6} {s['device']:<8} {cls_str}")
        print(
            f"Spatial matches (IoU>={args.iou_threshold}): {match['spatial_matches']} | "
            f"Class matches (same label + spatial): {match['class_matches']} | "
            f"Best IoU: {match['best_iou']:.3f}"
        )
        for det in match["details"]:
            print(
                f"  spatial pair: baseline[{det['a_index']}] {det['a_class']} <-> "
                f"challenger[{det['b_index']}] {det['b_class']} "
                f"IoU={det['iou']:.3f} class_match={det['class_match']}"
            )
        if base_dup_count:
            print(f"  baseline potential duplicates: {base_dup_count}")
            for f in base_dup:
                if f["potential_duplicate"]:
                    print(
                        f"    boxes {f['index_a']}&{f['index_b']} "
                        f"({f['class_a']}) IoU={f['iou']:.3f}"
                    )
        if chal_dup_count:
            print(f"  challenger potential duplicates: {chal_dup_count}")
            for f in chal_dup:
                if f["potential_duplicate"]:
                    print(
                        f"    boxes {f['index_a']}&{f['index_b']} "
                        f"({f['class_a']}) IoU={f['iou']:.3f}"
                    )
        print()

        for role, s, dup_count in (
            ("baseline", base, base_dup_count),
            ("challenger", chal, chal_dup_count),
        ):
            rows.append(
                {
                    "image_name": image,
                    "role": role,
                    "model_name": s["model_name"],
                    "detection_count": s["count"],
                    "class_names": ";".join(s["classes"]),
                    "confidence_scores": ";".join(f"{v:.4f}" for v in s["scores"]),
                    "inference_device": s["device"],
                    "iou_threshold": args.iou_threshold,
                    "spatial_matches_with_other_model": match["spatial_matches"],
                    "class_matches_with_other_model": match["class_matches"],
                    "best_cross_model_iou": f"{match['best_iou']:.4f}",
                    "intra_model_potential_duplicates": dup_count,
                }
            )

    if not rows:
        print("Error: no image pairs compared; CSV not written.", file=sys.stderr)
        sys.exit(1)

    try:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with output_csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote CSV summary: {output_csv} ({len(rows)} rows)")
    except OSError as exc:
        print(f"Error: could not write CSV {output_csv}: {exc}", file=sys.stderr)
        sys.exit(1)

    if had_error:
        print("Completed with missing/malformed files for some images.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
