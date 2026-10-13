# Model checkpoints

Checkpoint binaries are kept out of this repository. Download the app's primary
segmentation model from its upstream model card:

```powershell
.\.venv\Scripts\python.exe -m ml.src.download_models primary
```

The optional baseline used by the comparison tools can be fetched with:

```powershell
.\.venv\Scripts\python.exe -m ml.src.download_models baseline
```

Use `all` to fetch both checkpoints. The files are stored here locally and are
ignored by Git. The primary checkpoint is listed as AGPL-3.0 by its upstream
model card; that card also notes that the CarDD dataset requires a license
agreement. The baseline model card lists Apache-2.0. Review the upstream terms
before redistribution or commercial use.

- [Primary CarDD YOLOv8 segmentation model](https://huggingface.co/abdullahg7/cardd-yolov8s)
- [Optional YOLOv11 baseline](https://huggingface.co/vineetsarpal/yolov11n-car-damage)
