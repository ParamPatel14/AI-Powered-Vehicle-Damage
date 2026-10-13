"""Inspect HF repo metadata for a candidate second model (no download).

Verifies weight filenames, sizes, and licensing before downloading.
Default repo: abdullahg7/cardd-yolov8s
"""

import argparse
import sys

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError

REPO_ID = "abdullahg7/cardd-yolov8s"
WEIGHT_EXTS = (".pt", ".pth", ".bin", ".onnx", ".engine", ".tflite", ".mlpackage")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List HF repo files, sizes, and license without downloading."
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=REPO_ID,
        help=f"Hugging Face repo id (default: {REPO_ID}).",
    )
    return parser.parse_args()


def fmt_size(num_bytes) -> str:
    if num_bytes is None:
        return "unknown size"
    num = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024.0:
            return f"{num:,.1f} {unit} ({int(num_bytes):,} bytes)"
        num /= 1024.0
    return f"{num:,.1f} TB ({int(num_bytes):,} bytes)"


def main() -> None:
    args = parse_args()
    repo_id = args.repo
    api = HfApi()

    print(f"Inspecting Hugging Face repo: {repo_id}")
    print("No files will be downloaded by this script.\n")

    try:
        info = api.model_info(repo_id)
    except RepositoryNotFoundError:
        print(f"Error: repository not found: {repo_id}", file=sys.stderr)
        print("Check the repo id spelling and that it is public.", file=sys.stderr)
        sys.exit(1)
    except HfHubHTTPError as exc:
        print(f"Error: Hugging Face Hub HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: network/Hub failure while fetching model_info: {exc}", file=sys.stderr)
        print("Check your internet connection and retry.", file=sys.stderr)
        sys.exit(1)

    # --- Model-card / license info ---
    print("=== Model-card info ===")
    print(f"Repo id      : {info.id}")
    print(f"SHA          : {getattr(info, 'sha', 'unknown')}")
    print(f"Likes        : {getattr(info, 'likes', 'unknown')}")
    print(f"Downloads    : {getattr(info, 'downloads', 'unknown')}")
    print(f"Tags         : {', '.join(getattr(info, 'tags', []) or []) or '(none)'}")

    card = getattr(info, "cardData", None)
    license_val = None
    if isinstance(card, dict):
        license_val = card.get("license")
    elif card is not None:
        license_val = getattr(card, "license", None)
    # Fallback: Hub sometimes exposes license directly in tags.
    print(f"License      : {license_val if license_val else '(not declared in cardData)'}")
    if card:
        print(f"Card data    : {card}")
    else:
        print("Card data    : (none / not accessible)")
    print()

    # --- Exact filenames (metadata only, no download) ---
    try:
        filenames = api.list_repo_files(repo_id=repo_id, repo_type="model")
    except RepositoryNotFoundError:
        print(f"Error: repository not found when listing files: {repo_id}", file=sys.stderr)
        sys.exit(1)
    except HfHubHTTPError as exc:
        print(f"Error: Hub HTTP error while listing files: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: network failure while listing files: {exc}", file=sys.stderr)
        sys.exit(1)

    print("=== Repository filenames (exact, for inference selection) ===")
    for name in sorted(filenames):
        print(f"  {name}")
    print(f"\nTotal files: {len(filenames)}\n")

    # --- File sizes via paths info (still metadata only, no download) ---
    print("=== File sizes (metadata only) ===")
    try:
        infos = api.get_paths_info(
            repo_id=repo_id, repo_type="model", paths=sorted(filenames)
        )
        size_by_path = {e.path: getattr(e, "size", None) for e in infos}
        for name in sorted(filenames):
            print(f"  {name} - {fmt_size(size_by_path.get(name))}")
    except Exception as exc:
        print(f"Warning: could not fetch file sizes: {exc}")
        print("Filenames above are still valid; sizes unavailable.")
    print()

    # --- Inference-candidate weights ---
    candidates = [f for f in sorted(filenames) if f.lower().endswith(WEIGHT_EXTS)]
    print("=== Inference weight candidates ===")
    if not candidates:
        print("(No *.pt / *.pth / *.bin / *.onnx files found.)")
    else:
        for name in candidates:
            print(f"  {name}")
    print()
    print("How to select: prefer the Ultralytics *.pt checkpoint")
    print("(e.g. best.pt) for use with YOLO predict(); *.onnx/*.engine")
    print("are export formats and need a different runtime.")
    print("Download later with e.g.:")
    print(f"  huggingface-cli download {repo_id} <filename> "
          "--local-dir ml/weights --local-dir-use-symlinks False")


if __name__ == "__main__":
    main()
