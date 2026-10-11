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


class FoldTest(unittest.TestCase):
    def test_first_fold_anchors_to_the_nearest_corner(self) -> None:
        # 왼쪽·아래쪽에 가까움: 왼쪽 아래 모서리를 고정
        self.assertEqual(geo.fold_target({}, (100, 100, 500, 400), ROLLED_H, SCREEN), (100, 500 - ROLLED_H, 500, ROLLED_H))
        # 오른쪽·위쪽에 가까움: 오른쪽 위 모서리를 고정
        self.assertEqual(geo.fold_target({}, (1200, 50, 300, 200), ROLLED_H, SCREEN), (1200, 50, 300, ROLLED_H))
        # 접은 너비만 기억돼 있으면 그 너비로, 오른쪽 끝을 맞춤
        self.assertEqual(geo.fold_target({"rolled_width": 200}, (1200, 50, 300, 200), ROLLED_H, SCREEN), (1300, 50, 200, ROLLED_H))

    def test_fold_returns_to_the_remembered_rolled_spot(self) -> None:
        data = {"rolled_position_x": 900, "rolled_position_y": 600, "rolled_width": 250}
        self.assertEqual(geo.fold_target(data, (100, 100, 500, 400), ROLLED_H, SCREEN), (900, 600, 250, ROLLED_H))
        self.assertEqual(geo.fold_target(data, (1200, 50, 640, 480), ROLLED_H, SCREEN), (900, 600, 250, ROLLED_H))   # 펼친 메모가 어디 있든

    def test_locked_memo_folds_like_an_unlocked_one(self) -> None:
        plain = geo.fold_target({"unrolled_width": 500, "unrolled_height": 400}, (100, 100, 500, 400), ROLLED_H, SCREEN)
        locked = {"_locked": True, "unrolled_width": 500, "unrolled_height": 400}
        compact = (100, 100, *geo.LOCKED_SIZE)                       # 암호 입력용 크기로 떠 있는 창
        self.assertEqual(geo.own_size(locked, False, compact), (500, 400))
        self.assertEqual(geo.fold_target(locked, compact, ROLLED_H, SCREEN), plain)     # 너비도 자리도 같음
        self.assertEqual(plain[2], 500)


class UnfoldTest(unittest.TestCase):
    def data(self, **more):
        return {"position_x": 500, "position_y": 300, "unrolled_width": 400, "unrolled_height": 320, **more}

    def test_unfold_returns_to_the_remembered_unrolled_spot(self) -> None:
        self.assertEqual(geo.unfold_target(self.data(), (900, 600, 250, ROLLED_H), SCREEN, on_screen), (500, 300, 400, 320))

    def test_unfold_of_a_locked_memo_uses_the_password_size(self) -> None:
        box = geo.unfold_target(self.data(_locked=True), (900, 600, 250, ROLLED_H), SCREEN, on_screen)
        self.assertEqual(box, (500, 300, *geo.LOCKED_SIZE))

    def test_remembered_spot_on_another_monitor_is_kept(self) -> None:
        data = self.data(position_x=2000, position_y=200)
        rolled_on_left = (100, 700, 250, ROLLED_H)
        self.assertEqual(geo.unfold_target(data, rolled_on_left, LEFT, two_monitors), (2000, 200, 400, 320))
        # 그 모니터가 없어졌으면(자리가 어느 모니터에도 없음) 지금 모니터 안으로
        self.assertEqual(geo.unfold_target(data, rolled_on_left, LEFT, lambda box: LEFT), (LEFT.right() - 400, 200, 400, 320))

    def test_opens_beside_a_stack_it_would_cover(self) -> None:
        covers = lambda box: True
        left_stack = {"position_x": 0, "position_y": 700, "unrolled_width": 300, "unrolled_height": 300}
        box = geo.unfold_target(left_stack, (0, 700, 300, ROLLED_H), SCREEN, on_screen, stack=(0, 300), covers=covers)
        self.assertEqual(box, (300, 700 + ROLLED_H - 300, 300, 300))                    # 왼쪽에 쌓였으면 오른쪽에, 아래 끝을 맞춰서
        right_stack = {"position_x": 1300, "position_y": 700, "unrolled_width": 300, "unrolled_height": 300}
        box = geo.unfold_target(right_stack, (1300, 700, 300, ROLLED_H), SCREEN, on_screen, stack=(1300, 1600), covers=covers)
        self.assertEqual(box, (1000, 700 + ROLLED_H - 300, 300, 300))                   # 오른쪽에 쌓였으면 왼쪽에

    def test_stays_put_when_it_covers_nothing_or_there_is_no_room(self) -> None:
        data = {"position_x": 0, "position_y": 700, "unrolled_width": 300, "unrolled_height": 300}
        rolled = (0, 700, 300, ROLLED_H)
        remembered = (0, SCREEN.bottom() - 300, 300, 300)                               # 화면 안으로만 당김
        self.assertEqual(geo.unfold_target(data, rolled, SCREEN, on_screen, stack=(0, 300), covers=lambda box: False), remembered)
        self.assertEqual(geo.unfold_target(data, rolled, SCREEN, on_screen, stack=None, covers=lambda box: True), remembered)
        self.assertEqual(geo.unfold_target(data, rolled, SCREEN, on_screen, stack=(0, 1500), covers=lambda box: True), remembered)


class ShowTest(unittest.TestCase):
    DATA = {"position_x": 500, "position_y": 300, "unrolled_width": 400, "unrolled_height": 320,
            "rolled_position_x": 900, "rolled_position_y": 600, "rolled_width": 250}

    def test_hidden_window_goes_to_its_remembered_place(self) -> None:
        self.assertEqual(geo.show_target(self.DATA, True, False, False, (0, 0), ROLLED_H), (900, 600, 250, ROLLED_H))
        self.assertEqual(geo.show_target(self.DATA, False, False, False, (0, 0), ROLLED_H), (500, 300, 400, 320))

    def test_visible_window_stays_where_it_is(self) -> None:
        self.assertEqual(geo.show_target(self.DATA, True, True, True, (70, 80), ROLLED_H), (70, 80, 250, ROLLED_H))
        self.assertEqual(geo.show_target(self.DATA, False, False, True, (70, 80), ROLLED_H), (70, 80, 400, 320))
        # 접혀 있다가 펼친 상태로 바뀌는 경우: 세로는 펼친 자리의 것으로
        self.assertEqual(geo.show_target(self.DATA, False, True, True, (70, 80), ROLLED_H), (70, 300, 400, 320))

    def test_old_data_without_a_rolled_place(self) -> None:
        old = {"position_x": 120, "position_y": 90, "width": 480, "height": 600}
        self.assertEqual(geo.show_target(old, True, False, False, (0, 0), ROLLED_H), (120, 100, 480, ROLLED_H))
        self.assertEqual(geo.show_target({**old, "_locked": True}, False, False, False, (0, 0), ROLLED_H), (120, 90, *geo.LOCKED_SIZE))


if __name__ == "__main__":
    unittest.main()
