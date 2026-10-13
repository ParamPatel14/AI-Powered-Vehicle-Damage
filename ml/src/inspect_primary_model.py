"""Inspect the primary CarDD YOLOv8s checkpoint and evaluate its capabilities.

Checkpoint: ml/weights/cardd-yolov8s-v2.pt
- Loads the local checkpoint with Ultralytics (inference only).
- Prints task, class names, class count, model type, checkpoint path.
- Checks whether the model exposes boxes, masks, or both.
- Runs inference on sample_images/car1.jpg, car2.jpg, car3.jpg when present.
- Saves a JSON capability report to outputs/model_inspection/primary_model_report.json.

Does not train, modify, download models, or download datasets.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
from ultralytics import YOLO

DEFAULT_MODEL = Path("ml/weights/cardd-yolov8s-v2.pt")
DEFAULT_IMAGES = [
    Path("sample_images/car1.jpg"),
    Path("sample_images/car2.jpg"),
    Path("sample_images/car3.jpg"),
]
DEFAULT_REPORT = Path("outputs/model_inspection/primary_model_report.json")
IMAGE_SIZE = 640
CONF_THRESHOLD = 0.25


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect primary CarDD YOLOv8s checkpoint (no training, no download)."
    )
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--images", nargs="*", default=[str(p) for p in DEFAULT_IMAGES])
    parser.add_argument("--imgsz", type=int, default=IMAGE_SIZE)
    parser.add_argument("--conf", type=float, default=CONF_THRESHOLD)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    return parser.parse_args()


def get_device() -> str:
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def main() -> None:
    args = parse_args()
    model_path = Path(args.model)
    if not model_path.is_file():
        # Check first so Ultralytics does not attempt a download.
        print(f"Error: weights file not found: {model_path}", file=sys.stderr)
        sys.exit(1)

    device = get_device()
    print(f"Loading local checkpoint (inference only): {model_path}")
    print(f"Using device: {device}")
    try:
        model = YOLO(str(model_path))
    except Exception as exc:
        print(f"Error: failed to load YOLO checkpoint: {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Static model inspection (no inference yet) ---
    task = getattr(model, "task", "unknown")
    names = getattr(model, "names", {})
    class_names = [names[k] for k in sorted(names)] if isinstance(names, dict) else []
    num_classes = len(class_names)
    model_type = type(getattr(model, "model", model)).__name__

    print(f"Model task       : {task}")
    print(f"Model type       : {model_type}")
    print(f"Checkpoint path  : {model_path}")
    print(f"Number of classes: {num_classes}")
    print(f"Class names      : {class_names}")

    # Static capability hint: a 'segment' task / SegmentationModel
    # exposes both boxes and masks; a 'detect' task exposes boxes only.
    exposes_masks_static = task == "segment" or "segment" in model_type.lower()
    exposes_boxes_static = task in ("detect", "segment") or "detection" in model_type.lower() or exposes_masks_static
    print(
        f"Static capability: exposes_boxes={exposes_boxes_static}, "
        f"exposes_masks={exposes_masks_static}"
    )
    print()

    # --- Runtime inference on sample images ---
    image_results = []
    runtime_boxes_seen = False
    runtime_masks_seen = False
    had_inference_error = False

    for image_str in args.images:
        image_path = Path(image_str)
        if not image_path.is_file():
            print(f"Warning: image not found, skipping: {image_path}")
            image_results.append(
                {"image_path": str(image_path), "skipped": True, "reason": "file not found"}
            )
            continue

        print(f"Running inference on: {image_path} (imgsz={args.imgsz}, conf={args.conf})")
        try:
            results = model.predict(
                source=str(image_path),
                imgsz=args.imgsz,
                conf=args.conf,
                device=device,
                verbose=False,
            )
        except Exception as exc:
            print(f"Error: inference failed for {image_path}: {exc}", file=sys.stderr)
            had_inference_error = True
            image_results.append(
                {"image_path": str(image_path), "skipped": True, "reason": f"inference error: {exc}"}
            )
            continue

        if not results:
            print("  No results returned by model.")
            image_results.append(
                {
                    "image_path": str(image_path),
                    "detection_count": 0,
                    "class_names": [],
                    "confidence_scores": [],
                    "bboxes_xyxy": [],
                    "masks_available": False,
                    "num_masks": 0,
                }
            )
            continue

        result = results[0]
        boxes = getattr(result, "boxes", None)
        masks = getattr(result, "masks", None)
        has_boxes = boxes is not None and len(boxes) > 0
        has_masks = masks is not None and len(masks) > 0
        runtime_boxes_seen = runtime_boxes_seen or has_boxes
        runtime_masks_seen = runtime_masks_seen or has_masks

        detections = []
        if has_boxes:
            for box in boxes:
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                conf = float(box.conf[0].item())
                cls_id = int(box.cls[0].item())
                cls_name = str(names.get(cls_id, cls_id)) if isinstance(names, dict) else str(cls_id)
                detections.append(
                    {
                        "class_id": cls_id,
                        "class_name": cls_name,
                        "confidence": conf,
                        "bbox_xyxy": [x1, y1, x2, y2],
                    }
                )
                print(
                    f"  Detected: {cls_name} | conf={conf:.4f} | "
                    f"bbox=[{x1:.1f}, {y1:.1f}, {x2:.1f}, {y2:.1f}]"
                )
        else:
            print("  No detections.")

        mask_shape = list(masks.data.shape) if has_masks else []
        print(f"  Masks available: {has_masks} (num_masks={len(detections) if has_masks else 0})")

        image_results.append(
            {
                "image_path": str(image_path),
                "detection_count": len(detections),
                "class_names": [d["class_name"] for d in detections],
                "confidence_scores": [d["confidence"] for d in detections],
                "bboxes_xyxy": [d["bbox_xyxy"] for d in detections],
                "detections": detections,
                "masks_available": has_masks,
                "num_masks": len(detections) if has_masks else 0,
                "mask_tensor_shape": mask_shape,
            }
        )

    capability = {
        "checkpoint_path": str(model_path),
        "model_type": model_type,
        "model_task": task,
        "class_names": class_names,
        "num_classes": num_classes,
        "inference_device": device,
        "image_size": args.imgsz,
        "confidence_threshold": args.conf,
        "exposes_boxes_static": exposes_boxes_static,
        "exposes_masks_static": exposes_masks_static,
        "exposes_boxes_runtime": runtime_boxes_seen,
        "exposes_masks_runtime": runtime_masks_seen,
        "capability_summary": (
            "boxes+segmentation-masks" if runtime_masks_seen
            else "boxes-only" if runtime_boxes_seen
            else "no-detections-on-samples"
        ),
        "images": image_results,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    report_path = Path(args.report)
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(capability, indent=2), encoding="utf-8")
        print(f"\nSaved capability report: {report_path}")
    except OSError as exc:
        print(f"Error: could not write report {report_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Capability: {capability['capability_summary']} "
        f"(task={task}, type={model_type}, classes={num_classes})"
    )
    if had_inference_error:
        print("Completed with inference errors on some images.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
