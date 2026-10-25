"""Fine-tune the hazard model to detect stairs from Pascal VOC annotations."""

import argparse
import random
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import torch
import yaml
from ultralytics import YOLO


def convert_dataset(raw: Path, prepared: Path, seed: int = 0) -> Path:
    images = {Path(path.name[4:]).stem.lower(): path for path in raw.glob("img_*")}
    annotations = {Path(path.name[4:]).stem.lower(): path for path in raw.glob("xml_*")}
    pairs = sorted(set(images) & set(annotations))
    if len(pairs) < 10:
        raise RuntimeError(f"Need at least 10 complete stair pairs, found {len(pairs)}")

    if prepared.exists():
        shutil.rmtree(prepared)
    for split in ("train", "val"):
        (prepared / "images" / split).mkdir(parents=True)
        (prepared / "labels" / split).mkdir(parents=True)

    random.Random(seed).shuffle(pairs)
    split_at = max(1, int(len(pairs) * 0.8))
    box_count = 0
    for index, key in enumerate(pairs):
        root = ET.parse(annotations[key]).getroot()
        width = float(root.findtext("./size/width"))
        height = float(root.findtext("./size/height"))
        labels = []
        for stair in root.findall("object"):
            box = stair.find("bndbox")
            x1, y1, x2, y2 = [float(box.findtext(name)) for name in ("xmin", "ymin", "xmax", "ymax")]
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError(f"Invalid box in {annotations[key]}")
            labels.append(
                f"0 {(x1 + x2) / (2 * width):.6f} {(y1 + y2) / (2 * height):.6f} "
                f"{(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}"
            )
        if not labels:
            continue
        split = "train" if index < split_at else "val"
        image = images[key]
        shutil.copy2(image, prepared / "images" / split / image.name)
        (prepared / "labels" / split / f"{image.stem}.txt").write_text(
            "\n".join(labels), encoding="utf-8"
        )
        box_count += len(labels)

    data_yaml = prepared / "stairs.yaml"
    data_yaml.write_text(
        yaml.safe_dump({
            "path": str(prepared.resolve()),
            "train": "images/train",
            "val": "images/val",
            "names": {0: "stairs"},
        }, sort_keys=False),
        encoding="utf-8",
    )
    train_count = len(list((prepared / "images" / "train").iterdir()))
    val_count = len(list((prepared / "images" / "val").iterdir()))
    print(f"Prepared {train_count} train and {val_count} validation images with {box_count} boxes")
    return data_yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=Path("data/datasets/stairs_training/_hf_raw"))
    parser.add_argument("--prepared", type=Path, default=Path("data/training/stairs"))
    parser.add_argument("--weights", type=Path, default=Path("models/yolo11s.pt"))
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=8)
    args = parser.parse_args()

    data_yaml = convert_dataset(args.raw, args.prepared)
    model = YOLO(str(args.weights))
    device = 0 if torch.cuda.is_available() else "cpu"
    model.train(
        data=str(data_yaml), epochs=args.epochs, batch=args.batch, imgsz=640,
        patience=30, seed=0, project="runs", name="stairs", exist_ok=True,
        workers=0, device=device,
    )
    best = Path(model.trainer.save_dir) / "weights" / "best.pt"
    if not best.exists():
        raise FileNotFoundError(f"Training completed without {best}")
    metrics = YOLO(str(best)).val(data=str(data_yaml), split="val", workers=0, device=device)
    print(f"validation mAP50: {metrics.box.map50:.4f}")
    target = Path("models/hazards.pt")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, target)
    print(f"Replaced {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()