import numpy as np

from blindnav.detector import Detection
from blindnav.spatial import CAMERA_HEIGHT, SpatialAnalyzer, focal_length

W, H = 640, 480
BOX = (200, 300, 440, 440)


def synthetic_depth(slope: float, start: float = 3.0) -> np.ndarray:
    """Flat ground seen from 1.4 m, with a ramp inside BOX: slope > 0 rises (stairs up)."""
    f = focal_length((H, W))
    cy = H / 2
    rows = np.arange(H, dtype=np.float64)[:, None] - cy
    safe = np.where(rows > 1, rows, 1)
    ground = np.where(rows > 1, f * CAMERA_HEIGHT / safe, 40.0) * np.ones((H, W))
    denominator = rows / f + slope
    with np.errstate(divide="ignore", invalid="ignore"):
        ramp = np.where(denominator > 1e-6,
                        (CAMERA_HEIGHT + slope * start) / denominator, 40.0) * np.ones((H, W))
    inside = np.zeros((H, W), dtype=bool)
    inside[BOX[1]:BOX[3], BOX[0]:BOX[2]] = True
    on_ramp = inside & (ramp > start)
    depth = np.where(on_ramp, ramp, ground)
    return depth.astype(np.float32)


def stair_direction(slope: float) -> str | None:
    stairs = Detection(box=BOX, class_name="stairs", confidence=0.9)
    SpatialAnalyzer().analyze(synthetic_depth(slope), [stairs])
    return stairs.direction


def test_surface_rising_away_from_the_user_is_stairs_up():
    assert stair_direction(0.5) == "up"


def test_surface_falling_away_from_the_user_is_stairs_down():
    assert stair_direction(-0.5) == "down"


def test_flat_ground_has_no_stair_direction():
    assert stair_direction(0.0) is None
