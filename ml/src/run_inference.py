"""Baseline vehicle-damage inference with a local YOLO model.

Loads ml/weights/yolov11n-car-damage.pt via the Ultralytics API and
runs inference on a single image (no training, no model modification).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO

DEFAULT_MODEL = Path("ml/weights/yolov11n-car-damage.pt")
DEFAULT_OUTPUT_DIR = Path("outputs/baseline")
IMAGE_SIZE = 640
CONF_THRESHOLD = 0.25


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run baseline vehicle-damage inference on one image."
    )
    parser.add_argument(
        "image",
        type=str,
        help="Path to the input image (e.g. sample_images/car1.jpg).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=str(DEFAULT_MODEL),
        help=f"Path to local YOLO .pt file (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=IMAGE_SIZE,
        help=f"Inference image size (default: {IMAGE_SIZE}).",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=CONF_THRESHOLD,
        help=f"Confidence threshold (default: {CONF_THRESHOLD}).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    return parser.parse_args()


def get_device() -> str:
    """Use CUDA device 0 when available, otherwise CPU."""
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def main() -> None:
    args = parse_args()

    image_path = Path(args.image)
    if not image_path.is_file():
        print(f"Error: image file not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    model_path = Path(args.model)
    if not model_path.is_file():
        # Check first so Ultralytics does not try to download a missing model.
        print(f"Error: model file not found: {model_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = get_device()
    print(f"Loading local model: {model_path}")
    print(f"Using device: {device}")
    try:
        model = YOLO(str(model_path))
    except Exception as exc:
        print(f"Error: failed to load YOLO model: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Running inference on: {image_path} (imgsz={args.imgsz}, conf={args.conf})")
    try:
        results = model.predict(
            source=str(image_path),
            imgsz=args.imgsz,
            conf=args.conf,
            batch=1,
            device=device,
            verbose=False,
        )
    except Exception as exc:
        print(f"Error: inference failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if not results:
        print("No detections: model returned no results.")
        sys.exit(0)

    result = results[0]
    names = result.names  # class id -> class name mapping

    detections = []
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        print("No damage detected in this image.")
    else:
        for box in boxes:
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
            conf = float(box.conf[0].item())
            cls_id = int(box.cls[0].item())
            cls_name = str(names.get(cls_id, cls_id))
            detections.append(
                {
                    "class_id": cls_id,
                    "class_name": cls_name,
                    "confidence": conf,
                    "bbox_xyxy": [x1, y1, x2, y2],
                }
            )
            print(
                f"Detected: {cls_name} | conf={conf:.4f} | "
                f"bbox=[{x1:.1f}, {y1:.1f}, {x2:.1f}, {y2:.1f}]"
            )

    # Save annotated image next to JSON without touching unrelated files.
    stem = image_path.stem
    annotated_path = output_dir / f"{stem}_annotated.jpg"
    json_path = output_dir / f"{stem}_predictions.json"

    try:
        annotated = result.plot()  # BGR numpy array with boxes drawn
        ok = cv2.imwrite(str(annotated_path), annotated)
        if not ok:
            raise OSError("cv2.imwrite returned False")
        print(f"Saved annotated image: {annotated_path}")
    except Exception as exc:
        print(f"Error: failed to save annotated image: {exc}", file=sys.stderr)
        sys.exit(1)

    payload = {
        "image_path": str(image_path),
        "model_name": model_path.name,
        "model_path": str(model_path),
        "inference_device": device,
        "image_size": args.imgsz,
        "confidence_threshold": args.conf,
        "class_names": [d["class_name"] for d in detections],
        "confidence_scores": [d["confidence"] for d in detections],
        "bboxes_xyxy": [d["bbox_xyxy"] for d in detections],
        "detections": detections,
        "num_detections": len(detections),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved predictions JSON: {json_path}")
    except Exception as exc:
        print(f"Error: failed to save JSON: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
