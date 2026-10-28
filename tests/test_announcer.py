import math

from blindnav.announcer import Alert, Announcer, URGENT, WARNING, message, rank_alerts
from blindnav.detector import Detection
from blindnav.spatial import PathStatus


def path_alert(distance: float) -> Alert:
    return Alert("path", "obstacle", distance, 12, 0.8, URGENT, path_priority=True)


def test_new_obstacle_in_same_place_is_announced_again_after_the_path_cleared():
    announcer = Announcer()
    assert announcer.decide(0.0, [path_alert(2.0)]) is not None

    assert announcer.decide(10.0, []) is None  # path clear for a while
    assert announcer.decide(20.0, [path_alert(2.0)]) is not None


def test_same_obstacle_is_not_repeated_while_it_stays():
    announcer = Announcer()
    assert announcer.decide(0.0, [path_alert(2.0)]) is not None
    assert announcer.decide(1.0, [path_alert(2.0)]) is None
    assert announcer.decide(6.5, [path_alert(2.0)]) is None


def test_alert_with_unknown_distance_never_crashes_or_speaks():
    detection = Detection(box=(0, 0, 10, 10), class_name="person", confidence=0.9,
                          distance=math.nan, clock=12, in_path=True, track_id=1)
    assert rank_alerts([detection], None) == []


def test_named_hazard_without_alert_does_not_hide_a_blocked_path():
    # A pole matches the depth obstacle but is outside the walking box and untracked:
    # it produces no alert of its own, so the generic obstacle alert must remain.
    pole = Detection(box=(0, 0, 10, 10), class_name="pole", confidence=0.9,
                     distance=2.0, clock=1, in_path=False, track_id=None)
    path = PathStatus(ground_found=True, blocked=True, distance=2.0, clock=12)

    alerts = rank_alerts([pole], path)

    assert [a.key for a in alerts] == ["path"]
    assert message(alerts[0]).startswith("Stop!")
    assert alerts[0].level in {WARNING, URGENT}
