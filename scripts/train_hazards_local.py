"""Prepare and train SafeStride's custom hazard detector locally."""

import argparse
import random
import shutil
from collections import Counter
from pathlib import Path

import yaml
from ultralytics import YOLO

KEEP = {
    "Stairs": "stairs",
    "Electric Pole": "pole",
    "Building Pillar": "pillar",
    "Bin": "bin",
    "Parking Cone": "cone",
    "Obstacle": "obstacle",
}
BACKGROUND_PER_HAZARD_IMAGE = 0.5


def find_dataset_root(source: Path) -> Path:
    candidates = [source] if (source / "data.yaml").exists() else list(source.rglob("data.yaml"))
    if not candidates:
        raise FileNotFoundError(f"No data.yaml found under {source}")
    return candidates[0].parent


def polygon_to_box(values: list[float]) -> tuple[float, float, float, float]:
    if len(values) == 4:
        return tuple(values)  # type: ignore[return-value]
    xs, ys = values[0::2], values[1::2]
    x1, x2 = max(min(xs), 0.0), min(max(xs), 1.0)
    y1, y2 = max(min(ys), 0.0), min(max(ys), 1.0)
    return (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1


def convert_label(label_path: Path, old_to_new: dict[int, int]) -> list[str]:
    converted = []
    if not label_path.exists():
        return converted
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts or int(parts[0]) not in old_to_new:
            continue
        cx, cy, width, height = polygon_to_box([float(value) for value in parts[1:]])
        if width * height < 1e-5:
            continue
        converted.append(
            f"{old_to_new[int(parts[0])]} {cx:.6f} {cy:.6f} {width:.6f} {height:.6f}"
        )
    return converted


def prepare_dataset(source: Path, destination: Path) -> Path:
    dataset_root = find_dataset_root(source)
    source_names = yaml.safe_load((dataset_root / "data.yaml").read_text(encoding="utf-8"))["names"]
    old_to_new = {source_names.index(old): index for index, old in enumerate(KEEP)}
    random.seed(0)
    stats = Counter()

    for split in ("train", "valid", "test"):
        source_images = dataset_root / split / "images"
        source_labels = dataset_root / split / "labels"
        destination_images = destination / split / "images"
        destination_labels = destination / split / "labels"
        destination_images.mkdir(parents=True, exist_ok=True)
        destination_labels.mkdir(parents=True, exist_ok=True)

        hazard_images = []
        background_images = []
        for image in sorted(source_images.iterdir()):
            lines = convert_label(source_labels / f"{image.stem}.txt", old_to_new)
            item = (image, lines)
            (hazard_images if lines else background_images).append(item)

        if split == "train":
            background_images = random.sample(
                background_images,
                min(len(background_images), int(len(hazard_images) * BACKGROUND_PER_HAZARD_IMAGE)),
            )

        for image, lines in hazard_images + background_images:
            shutil.copy2(image, destination_images / image.name)
            (destination_labels / f"{image.stem}.txt").write_text(
                "\n".join(lines), encoding="utf-8"
            )
            for line in lines:
                class_name = list(KEEP.values())[int(line.split()[0])]
                stats[f"{split}/{class_name}"] += 1
        stats[f"{split}/images_with_hazards"] = len(hazard_images)
        stats[f"{split}/background_images"] = len(background_images)

    data_yaml = destination / "hazards.yaml"
    data_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(destination),
                "train": "train/images",
                "val": "valid/images",
                "test": "test/images",
                "names": dict(enumerate(KEEP.values())),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    print(f"Prepared dataset: {destination}")
    for key, value in sorted(stats.items()):
        print(f"{key}: {value}")
    return data_yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--prepared", type=Path, default=Path("data/training/hazards"))
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()

    data_yaml = prepare_dataset(args.source, args.prepared)
    model = YOLO("yolo11s.pt")
    project_dir = Path(__file__).resolve().parents[1] / "runs"
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=640,
        patience=15,
        seed=0,
        project=str(project_dir),
        name="hazards",
        exist_ok=True,
        workers=0,
        device=0,
    )

    best = project_dir / "hazards" / "weights" / "best.pt"
    if not best.exists():
        raise FileNotFoundError(f"Training completed without {best}")
    metrics = YOLO(str(best)).val(data=str(data_yaml), split="test", plots=True, workers=0, device=0)
    print(f"test mAP50: {metrics.box.map50:.4f}")
    print(f"test mAP50-95: {metrics.box.map:.4f}")
    target = Path("models/hazards.pt")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, target)
    print(f"Saved: {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
