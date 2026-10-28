import pytest
import time

from blindnav.navigation import NavigationManager


def make_route():
    return {
        "geometry": {"coordinates": [[0.0, 0.0], [0.002, 0.0]]},
        "legs": [{"steps": []}],
        "distance": 222.4,
    }


def test_position_between_route_vertices_is_on_route_and_uses_route_distance():
    manager = NavigationManager(deviation_meters=50)
    manager.set_route(make_route(), (0.0, 0.002))

    update = manager.update(0.00025, 0.001)

    assert update.off_route is False
    assert update.distance_remaining == pytest.approx(111.2, abs=1)
    assert manager.snapshot()["distance_remaining"] == pytest.approx(111.2, abs=1)


def test_navigation_snapshot_includes_route_geometry_for_map():
    manager = NavigationManager()
    manager.set_route(make_departure_route(), (13.028, 77.498))

    assert manager.snapshot()["route_geometry"] == [
        (13.027282, 77.497048),
        (13.027951, 77.497156),
        (13.027949, 77.49789),
    ]


def test_off_route_requires_two_consecutive_gps_readings():
    manager = NavigationManager(deviation_meters=50)
    manager.set_route(make_route(), (0.0, 0.002))

    first_reading = manager.update(0.002, 0.001, accuracy=5)
    confirmed_reading = manager.update(0.002, 0.001, accuracy=5)

    assert first_reading.off_route is False
    assert confirmed_reading.off_route is True
    assert confirmed_reading.message == "You are off the planned route. Stop and request a new route."


def test_off_route_threshold_accounts_for_gps_accuracy():
    manager = NavigationManager(deviation_meters=50)
    manager.set_route(make_route(), (0.0, 0.002))

    update = manager.update(0.0008, 0.001, accuracy=40)

    assert update.off_route is False


def make_departure_route():
    return {
        "geometry": {
            "coordinates": [
                [77.497048, 13.027282],
                [77.497156, 13.027951],
                [77.49789, 13.027949],
            ]
        },
        "legs": [{"steps": [
            {"distance": 75, "maneuver": {
                "type": "depart", "modifier": "right", "bearing_after": 9,
                "location": [77.497048, 13.027282],
            }},
            {"distance": 80, "maneuver": {
                "type": "turn", "modifier": "right", "bearing_after": 90,
                "location": [77.497156, 13.027951],
            }},
            {"distance": 0, "maneuver": {
                "type": "arrive", "modifier": "right", "bearing_after": 0,
                "location": [77.498, 13.028],
            }},
        ]}],
        "distance": 155,
    }


def test_departure_corrects_compass_then_guides_along_first_road():
    manager = NavigationManager()
    manager.set_route(make_departure_route(), (13.028, 77.498))
    aligned = manager.update(13.027282, 77.497048, heading=9,
                             heading_timestamp=time.time() * 1000)

    assert aligned.message == "You are facing the mapped road. Once safely on it, walk straight for 75 meters, then turn right."


def test_stale_camera_direction_does_not_issue_walk_instruction():
    manager = NavigationManager()
    manager.set_route(make_departure_route(), (13.028, 77.498))
    update = manager.update(13.027282, 77.497048, heading=95,
                            heading_timestamp=1)

    assert update.message == "Camera direction unavailable. Stop until the camera direction can be checked."


def test_east_facing_phone_is_told_to_turn_left_for_northbound_departure():
    manager = NavigationManager()
    manager.set_route(make_departure_route(), (13.028, 77.498))
    update = manager.update(13.027282, 77.497048, heading=95,
                            heading_timestamp=time.time() * 1000)

    assert update.message == "Turn left to face the road. Stop when aligned."


def test_nearly_opposite_heading_is_told_to_turn_around():
    manager = NavigationManager()
    manager.set_route(make_departure_route(), (13.028, 77.498))
    update = manager.update(13.027282, 77.497048, heading=188,
                            heading_timestamp=time.time() * 1000)

    assert update.message == "Turn around to face the road. Stop when aligned."


def test_turn_is_not_skipped_and_final_approach_stays_on_last_road_segment():
    manager = NavigationManager()
    manager.set_route(make_departure_route(), (13.028, 77.498))
    manager.update(13.027282, 77.497048, heading=9, heading_timestamp=time.time() * 1000)

    at_turn = manager.update(13.027951, 77.497156, heading=9,
                             heading_timestamp=time.time() * 1000)
    assert at_turn.step_index == 1
    assert at_turn.message == "Turn right to face the next road. Stop when aligned."

    after_alignment = manager.update(13.027951, 77.497156, heading=90,
                                     heading_timestamp=time.time() * 1000)
    assert after_alignment.step_index == 1
    assert after_alignment.message == "Aligned. walk straight for 80 meters to the destination."


def test_turn_advances_when_gps_sample_jumps_past_waypoint():
    manager = NavigationManager(deviation_meters=30)
    manager.set_route(make_departure_route(), (13.028, 77.498))
    manager.update(13.02760, 77.49710, heading=9,
                   heading_timestamp=time.time() * 1000)

    after_turn = manager.update(13.028069, 77.497156, heading=9, accuracy=5,
                               heading_timestamp=time.time() * 1000)

    assert after_turn.step_index == 1
    assert after_turn.message == "Turn right to face the next road. Stop when aligned."


def test_arrival_is_announced_once_and_not_repeated():
    manager = NavigationManager(repeat_after=0.0)
    manager.set_route(make_route(), (0.0, 0.002))

    first = manager.update(0.0, 0.002)
    second = manager.update(0.0, 0.002)

    assert first.message == "You have arrived at your destination."
    assert first.arrived is True
    assert second.message is None
    assert second.arrived is True
    assert second.event_id == first.event_id


def test_arrival_stays_latched_when_gps_jitters_outside_the_arrival_radius():
    manager = NavigationManager(repeat_after=0.0)
    manager.set_route(make_route(), (0.0, 0.002))
    manager.update(0.0, 0.002)

    jitter = manager.update(0.0, 0.0018)  # ~22 m from the destination, then ~40 m

    assert jitter.arrived is True
    assert jitter.message is None


def fresh_heading():
    return time.time() * 1000


def test_walk_instruction_counts_down_the_distance_to_the_next_turn():
    manager = NavigationManager(repeat_after=0.0)
    manager.set_route(make_departure_route(), (13.028, 77.498))

    at_start = manager.update(13.027282, 77.497048, heading=9, heading_timestamp=fresh_heading())
    later = manager.update(13.027750, 77.497110, heading=9, heading_timestamp=fresh_heading())

    assert at_start.message.endswith("walk straight for 75 meters, then turn right.")
    assert later.message.endswith("walk straight for 25 meters, then turn right.")
    assert later.step_index == 0


def test_shrinking_distance_alone_is_not_re_spoken_before_the_repeat_timer():
    manager = NavigationManager(repeat_after=60.0)
    manager.set_route(make_departure_route(), (13.028, 77.498))

    first = manager.update(13.027282, 77.497048, heading=9, heading_timestamp=fresh_heading())
    second = manager.update(13.027500, 77.497080, heading=9, heading_timestamp=fresh_heading())

    assert first.message is not None
    assert second.message is None
    assert second.event_id == first.event_id