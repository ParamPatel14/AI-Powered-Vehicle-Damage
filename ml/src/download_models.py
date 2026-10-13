"""Download the upstream checkpoints used by the app and ML comparison tools."""

import argparse
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEIGHTS_DIR = PROJECT_ROOT / "ml" / "weights"
CHECKPOINTS = {
    "primary": (
        "abdullahg7/cardd-yolov8s",
        "v2.0/best.pt",
        "cardd-yolov8s-v2.pt",
    ),
    "baseline": (
        "vineetsarpal/yolov11n-car-damage",
        "best.pt",
        "yolov11n-car-damage.pt",
    ),
}


def download_checkpoint(name: str, force: bool = False) -> Path:
    repo_id, filename, local_name = CHECKPOINTS[name]
    destination = WEIGHTS_DIR / local_name
    if destination.is_file() and not force:
        print(f"Already present: {destination.relative_to(PROJECT_ROOT)}")
        return destination

    source = hf_hub_download(repo_id=repo_id, filename=filename)
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    print(f"Downloaded {repo_id}/{filename} -> {destination.relative_to(PROJECT_ROOT)}")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=("primary", "baseline", "all"), default="primary", nargs="?")
    parser.add_argument("--force", action="store_true", help="Replace an existing local checkpoint.")
    args = parser.parse_args()

    names = tuple(CHECKPOINTS) if args.model == "all" else (args.model,)
    for name in names:
        download_checkpoint(name, force=args.force)


if __name__ == "__main__":
    main()
