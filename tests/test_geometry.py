"""메모 창의 위치·크기 규칙 테스트. 창을 띄우지 않고 숫자만으로 확인합니다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QRect

from ui import memo_geometry as geo

SCREEN = QRect(0, 0, 1600, 900)
LEFT, RIGHT = QRect(0, 0, 1600, 900), QRect(1600, 0, 1600, 900)
ROLLED_H = 53


def on_screen(box):
    return SCREEN


def two_monitors(box):
    return LEFT if box[0] + box[2] / 2 < 1600 else RIGHT


class RememberTest(unittest.TestCase):
    def test_each_state_keeps_its_own_place_and_size(self) -> None:
        data = {}
        geo.remember(data, False, (10, 20, 400, 300))
        self.assertEqual((data["position_x"], data["position_y"], data["unrolled_width"], data["unrolled_height"]), (10, 20, 400, 300))
        self.assertEqual((data["width"], data["height"]), (400, 300))
        geo.remember(data, True, (900, 600, 250, ROLLED_H))
        self.assertEqual((data["rolled_position_x"], data["rolled_position_y"], data["rolled_width"]), (900, 600, 250))
        self.assertEqual((data["position_x"], data["position_y"], data["unrolled_width"], data["unrolled_height"]), (10, 20, 400, 300))
        geo.remember(data, False, (30, 40, 640, 480))
        self.assertEqual((data["rolled_position_x"], data["rolled_position_y"], data["rolled_width"]), (900, 600, 250))

    def test_locked_size_is_never_remembered_as_the_memo_size(self) -> None:
        data = {"_locked": True, "unrolled_width": 500, "unrolled_height": 400, "width": 500, "height": 400}
        self.assertTrue(geo.is_locked_compact(data, rolled=False))
        geo.remember(data, False, (5, 6, *geo.LOCKED_SIZE))
        self.assertEqual((data["position_x"], data["position_y"]), (5, 6))               # 자리는 기억하고
        self.assertEqual((data["unrolled_width"], data["unrolled_height"]), (500, 400))  # 크기는 그대로
        self.assertFalse(geo.is_locked_compact(data, rolled=True))                       # 접혀 있으면 해당 없음
        geo.remember(data, True, (7, 8, 410, ROLLED_H))
        self.assertEqual(data["rolled_width"], 410)

    def test_sizes(self) -> None:
        self.assertEqual(geo.unrolled_size({"_locked": True, "unrolled_width": 500, "unrolled_height": 400}), geo.LOCKED_SIZE)
        self.assertEqual(geo.unrolled_size({"unrolled_width": 500, "unrolled_height": 400}), (500, 400))
        self.assertEqual(geo.saved_unrolled_size({"width": 420, "height": 310}), (420, 310))       # 예전 형식
        self.assertEqual(geo.saved_unrolled_size({"unrolled_width": 10, "unrolled_height": 10}), (300, 300))   # 잘못된 값
        self.assertEqual(geo.saved_unrolled_size({}, default_height=444), (500, 444))


class ClampTest(unittest.TestCase):
    def test_keeps_the_window_inside_the_work_area(self) -> None:
        self.assertEqual(geo.clamp(SCREEN, 100, 100, 300, 200), (100, 100))
        self.assertEqual(geo.clamp(SCREEN, 1500, 800, 300, 200), (SCREEN.right() - 300, SCREEN.bottom() - 200))
        self.assertEqual(geo.clamp(SCREEN, -50, -50, 300, 200), (0, 0))
        self.assertEqual(geo.clamp(RIGHT, 100, 100, 300, 200), (1600, 100))             # 다른 모니터의 영역 안으로


class CornerTest(unittest.TestCase):
    """위치 고정이 없을 때: 왼쪽 아래 모서리를 두고 위·오른쪽으로. 넘치면 아래·왼쪽으로."""

    def test_grows_up_and_right_from_the_bottom_left_corner(self) -> None:
        self.assertEqual(geo.grow_from_corner((100, 600, 250, ROLLED_H), (400, 320), SCREEN), (100, 600 + ROLLED_H - 320))
        self.assertEqual(geo.grow_from_corner((100, 300, 400, 320), (250, ROLLED_H), SCREEN), (100, 300 + 320 - ROLLED_H))

    def test_grows_down_when_there_is_no_room_above(self) -> None:
        self.assertEqual(geo.grow_from_corner((100, 10, 250, ROLLED_H), (400, 320), SCREEN), (100, 10))

    def test_grows_left_when_there_is_no_room_on_the_right(self) -> None:
        self.assertEqual(geo.grow_from_corner((1400, 600, 150, ROLLED_H), (400, 320), SCREEN), (1400 + 150 - 400, 600 + ROLLED_H - 320))

    def test_both_at_the_top_right(self) -> None:
        self.assertEqual(geo.grow_from_corner((1400, 0, 150, ROLLED_H), (400, 320), SCREEN), (1150, 0))

    def test_still_too_big_is_pulled_inside(self) -> None:
        self.assertEqual(geo.grow_from_corner((0, 0, 100, ROLLED_H), (2000, 1200), SCREEN), (0, 0))      # 화면보다 크면 왼쪽 위에 맞춤


class FoldTest(unittest.TestCase):
    def test_fold_keeps_the_bottom_left_corner(self) -> None:
        self.assertEqual(geo.fold_target({}, (100, 100, 500, 400), ROLLED_H, SCREEN), (100, 500 - ROLLED_H, 500, ROLLED_H))
        self.assertEqual(geo.fold_target({"rolled_width": 200}, (1200, 50, 300, 200), ROLLED_H, SCREEN), (1200, 250 - ROLLED_H, 200, ROLLED_H))

    def test_pinned_fold_goes_to_the_pin(self) -> None:
        data = {"rolled_width": 250}
        self.assertEqual(geo.fold_target(data, (100, 100, 500, 400), ROLLED_H, SCREEN, pinned=(900, 600)), (900, 600, 250, ROLLED_H))

    def test_locked_memo_folds_to_its_real_width(self) -> None:
        locked = {"_locked": True, "unrolled_width": 500, "unrolled_height": 400}
        compact = (100, 100, *geo.LOCKED_SIZE)                       # 암호 입력용 크기로 떠 있는 창
        self.assertEqual(geo.own_size(locked, False, compact), (500, 400))
        self.assertEqual(geo.fold_target(locked, compact, ROLLED_H, SCREEN), (100, 100 + geo.LOCKED_SIZE[1] - ROLLED_H, 500, ROLLED_H))


class UnfoldTest(unittest.TestCase):
    DATA = {"position_x": 500, "position_y": 300, "unrolled_width": 400, "unrolled_height": 320}

    def test_unfold_grows_from_the_rolled_memo(self) -> None:
        self.assertEqual(geo.unfold_target(self.DATA, (900, 600, 250, ROLLED_H), SCREEN), (900, 600 + ROLLED_H - 320, 400, 320))

    def test_pinned_unfold_goes_to_the_pin(self) -> None:
        self.assertEqual(geo.unfold_target(self.DATA, (900, 600, 250, ROLLED_H), SCREEN, pinned=(2000, 200)), (2000, 200, 400, 320))

    def test_unfold_of_a_locked_memo_uses_the_password_size(self) -> None:
        box = geo.unfold_target({**self.DATA, "_locked": True}, (900, 600, 250, ROLLED_H), SCREEN)
        self.assertEqual(box, (900, 600 + ROLLED_H - geo.LOCKED_SIZE[1], *geo.LOCKED_SIZE))


class PinTest(unittest.TestCase):
    LAYOUT = [(0, 0, 1600, 900), (1600, 0, 1600, 900)]

    def test_pin_is_used_only_with_the_same_monitors(self) -> None:
        data = {}
        self.assertFalse(geo.has_pin(data, False))
        geo.set_pin(data, False, (2000, 200), (1600, 0, 1600, 900))
        self.assertTrue(geo.has_pin(data, False))
        self.assertFalse(geo.has_pin(data, True))                    # 상태마다 따로
        self.assertEqual(geo.pinned_spot(data, False, self.LAYOUT), (2000, 200))
        self.assertIsNone(geo.pinned_spot(data, False, [(0, 0, 1600, 900)]))                       # 그 모니터를 뗌
        self.assertIsNone(geo.pinned_spot(data, False, [(0, 0, 1600, 900), (1600, 0, 1920, 1080)]))  # 해상도가 바뀜
        geo.clear_pin(data, False)
        self.assertIsNone(geo.pinned_spot(data, False, self.LAYOUT))

    def test_broken_pin_is_ignored(self) -> None:
        for broken in ({"x": 1}, {"x": "a", "y": 2, "screen": [0, 0, 1, 1]}, "nonsense"):
            self.assertIsNone(geo.pinned_spot({"unrolled_pin": broken}, False, self.LAYOUT))

    def test_pins_stay_on_this_pc(self) -> None:
        from core.sync_worker import is_device_key
        self.assertTrue(is_device_key(geo.pin_key(True)))
        self.assertTrue(is_device_key(geo.pin_key(False)))


class ShowTest(unittest.TestCase):
    DATA = {"position_x": 500, "position_y": 300, "unrolled_width": 400, "unrolled_height": 320,
            "rolled_position_x": 900, "rolled_position_y": 600, "rolled_width": 250}

    def test_hidden_window_goes_to_its_last_place_or_pin(self) -> None:
        self.assertEqual(geo.show_target(self.DATA, True, False, (0, 0), ROLLED_H), (900, 600, 250, ROLLED_H))
        self.assertEqual(geo.show_target(self.DATA, False, False, (0, 0), ROLLED_H), (500, 300, 400, 320))
        self.assertEqual(geo.show_target(self.DATA, False, False, (0, 0), ROLLED_H, pinned=(10, 20)), (10, 20, 400, 320))

    def test_visible_window_stays_where_it_is(self) -> None:
        self.assertEqual(geo.show_target(self.DATA, True, True, (70, 80), ROLLED_H), (70, 80, 250, ROLLED_H))
        self.assertEqual(geo.show_target(self.DATA, False, True, (70, 80), ROLLED_H, pinned=(10, 20)), (70, 80, 400, 320))

    def test_old_data_without_a_rolled_place(self) -> None:
        old = {"position_x": 120, "position_y": 90, "width": 480, "height": 600}
        self.assertEqual(geo.show_target(old, True, False, (0, 0), ROLLED_H), (120, 100, 480, ROLLED_H))
        self.assertEqual(geo.show_target({**old, "_locked": True}, False, False, (0, 0), ROLLED_H), (120, 90, *geo.LOCKED_SIZE))


if __name__ == "__main__":
    unittest.main()
