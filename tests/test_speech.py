import queue
import threading

import numpy as np

from blindnav.announcer import Alert, URGENT, WARNING
from blindnav.speech import LiveSpeaker


def make_speaker():
    speaker = object.__new__(LiveSpeaker)  # skip the audio thread: only the bookkeeping is tested
    speaker.queue = queue.Queue()
    speaker.generation = 0
    speaker.lock = threading.Lock()
    return speaker


def alert(level):
    return Alert("path", "obstacle", 2.0, 12, 0.9, level, path_priority=True)


class FakeStream:
    def __init__(self, on_write=None):
        self.written = []
        self.on_write = on_write

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, chunk):
        self.written.append(len(chunk))
        if self.on_write:
            self.on_write(len(self.written))


class FakeSoundDevice:
    def __init__(self, stream):
        self.stream = stream

    def OutputStream(self, **kwargs):
        assert kwargs["channels"] == 2
        return self.stream


def test_warning_does_not_interrupt_or_flush():
    speaker = make_speaker()
    speaker.say(alert(WARNING), "one")
    speaker.say(alert(WARNING), "two")

    assert speaker.generation == 0
    assert speaker.queue.qsize() == 2


def test_urgent_alert_drops_queued_alerts_and_bumps_generation():
    speaker = make_speaker()
    speaker.say(alert(WARNING), "old")
    speaker.say(alert(URGENT), "stop")

    assert speaker.generation == 1
    assert speaker.queue.qsize() == 1
    generation, queued, text = speaker.queue.get_nowait()
    assert (generation, text) == (1, "stop")


def test_playing_clip_is_abandoned_when_an_urgent_alert_arrives():
    speaker = make_speaker()
    stream = FakeStream(on_write=lambda n: speaker.say(alert(URGENT), "stop") if n == 2 else None)
    clip = np.zeros((LiveSpeaker.CHUNK * 10, 2), dtype=np.float32)

    speaker._play(FakeSoundDevice(stream), clip, generation=0)

    assert len(stream.written) == 2  # stopped right after the interruption, not after 10 chunks


def test_clip_plays_completely_without_interruption():
    speaker = make_speaker()
    stream = FakeStream()
    clip = np.zeros((LiveSpeaker.CHUNK * 3 + 5, 2), dtype=np.float32)

    speaker._play(FakeSoundDevice(stream), clip, generation=0)

    assert stream.written == [LiveSpeaker.CHUNK] * 3 + [5]
