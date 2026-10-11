"""메모 알림.

메모의 'reminder' 값 하나로 표현합니다.
    {"at": "2026-10-12T15:00:00", "repeat": "none", "cron": ""}
 - at       : 다음에 울릴 시각 (그 PC의 지역 시각). 반복 알림은 이 값의 시·분이 매번 울리는 시각입니다.
 - repeat   : "none"(한 번) / "daily"(매일) / "weekdays"(평일마다) / "weekly"(매주) / "monthly"(매월) / "cron"(크론식)
 - weekdays : repeat 가 "weekly" 일 때 울릴 요일들. 0(월)~6(일). 예: [0, 2]
 - days     : repeat 가 "monthly" 일 때 울릴 날짜들. 1~31. 그 달에 없는 날짜는 그 달의 마지막 날에 울립니다. 예: [1, 15]
 - cron     : repeat 가 "cron" 일 때의 크론식. "분 시 일 월 요일" 다섯 칸.

크론식 예
    0 9 * * 1-5      평일 오전 9시
    */30 9-18 * * *  9시~18시 사이 30분마다
    0 18 * * 5       매주 금요일 오후 6시
    0 9 1,15 * *     매월 1일과 15일 오전 9시
요일은 0~6(일~토)이고 7도 일요일입니다. '일'과 '요일'을 둘 다 지정하면 둘 중 하나만 맞아도 울립니다. (일반 크론과 같은 규칙)
"""
import calendar
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

REPEATS = ("none", "daily", "weekdays", "weekly", "monthly", "cron")
REPEAT_LABELS = {
    "none": "한 번만", "daily": "매일", "weekdays": "평일마다 (월~금)", "weekly": "매주",
    "monthly": "매월", "cron": "크론식으로 지정",
}
_FIELDS = (("분", 0, 59), ("시", 0, 23), ("일", 1, 31), ("월", 1, 12), ("요일", 0, 7))
_WEEKDAYS = "월화수목금토일"


class CronSpec:
    """풀어 놓은 크론식. 칸마다 허용되는 값의 집합을 가집니다."""

    def __init__(self, minutes: Set[int], hours: Set[int], days: Set[int], months: Set[int], weekdays: Set[int],
                 day_any: bool, weekday_any: bool) -> None:
        self.minutes, self.hours, self.days, self.months, self.weekdays = minutes, hours, days, months, weekdays
        self.day_any, self.weekday_any = day_any, weekday_any

    def day_matches(self, moment: datetime) -> bool:
        if moment.month not in self.months:
            return False
        cron_weekday = (moment.weekday() + 1) % 7          # 파이썬: 월=0 … 일=6  →  크론: 일=0 … 토=6
        by_day, by_weekday = moment.day in self.days, cron_weekday in self.weekdays
        if self.day_any and self.weekday_any:
            return True
        if self.day_any:
            return by_weekday
        if self.weekday_any:
            return by_day
        return by_day or by_weekday


def _parse_field(text: str, name: str, low: int, high: int) -> Set[int]:
    values: Set[int] = set()
    for part in text.split(","):
        if not part:
            raise ValueError(f"'{name}' 칸이 비어 있습니다.")
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            if not step_text.isdigit() or int(step_text) < 1:
                raise ValueError(f"'{name}' 칸의 간격(/ 뒤)은 1 이상의 숫자여야 합니다.")
            step = int(step_text)
        if part == "*":
            start, end = low, high
        elif "-" in part:
            a, b = part.split("-", 1)
            if not (a.isdigit() and b.isdigit()):
                raise ValueError(f"'{name}' 칸의 범위는 '시작-끝' 숫자여야 합니다.")
            start, end = int(a), int(b)
        elif part.isdigit():
            start = int(part)
            end = high if step > 1 else start       # "5/10" 은 5부터 10 간격으로
        else:
            raise ValueError(f"'{name}' 칸을 읽을 수 없습니다: {part}")
        if start < low or end > high or start > end:
            raise ValueError(f"'{name}' 칸은 {low}~{high} 사이여야 합니다.")
        values.update(range(start, end + 1, step))
    return values


def parse_cron(expr: Any) -> CronSpec:
    """크론식을 풀어 줍니다. 형식이 틀리면 무엇이 틀렸는지 적은 ValueError 를 냅니다."""
    parts = str(expr or "").split()
    if len(parts) != 5:
        raise ValueError("크론식은 '분 시 일 월 요일' 다섯 칸이어야 합니다. 예: 0 9 * * 1-5")
    sets: List[Set[int]] = [_parse_field(text, name, low, high) for text, (name, low, high) in zip(parts, _FIELDS)]
    weekdays = {0 if d == 7 else d for d in sets[4]}
    return CronSpec(sets[0], sets[1], sets[2], sets[3], weekdays, day_any=parts[2] == "*", weekday_any=parts[4] == "*")


def next_cron(expr: Any, after: datetime) -> datetime:
    """after 보다 뒤에 오는 첫 번째 시각. (5년 안에 없으면 ValueError: 2월 30일 같은 식)"""
    spec = parse_cron(expr)
    moment = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    day = moment.replace(hour=0, minute=0)
    for _ in range(366 * 5):
        if spec.day_matches(day):
            for hour in sorted(spec.hours):
                for minute in sorted(spec.minutes):
                    candidate = day.replace(hour=hour, minute=minute)
                    if candidate >= moment:
                        return candidate
        day += timedelta(days=1)
    raise ValueError("이 크론식에 맞는 날짜가 없습니다.")


def _parse_at(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _int_list(values: Any, low: int, high: int) -> List[int]:
    """values 에서 low~high 사이의 정수만 골라, 겹치지 않게 작은 것부터 늘어놓습니다."""
    if not isinstance(values, (list, tuple, set)):
        return []
    return sorted({v for v in values if isinstance(v, int) and not isinstance(v, bool) and low <= v <= high})


def normalize(reminder: Any) -> Optional[Dict[str, Any]]:
    """저장된 값을 점검해 쓸 수 있는 알림으로 돌려줍니다. 쓸 수 없으면 None."""
    if not isinstance(reminder, dict):
        return None
    at = _parse_at(reminder.get("at"))
    repeat = reminder.get("repeat", "none")
    if at is None or repeat not in REPEATS:
        return None
    cron = str(reminder.get("cron", "") or "")
    if repeat == "cron":
        try:
            parse_cron(cron)
        except ValueError:
            return None
    out = {"at": at.replace(microsecond=0).isoformat(), "repeat": repeat, "cron": cron if repeat == "cron" else ""}
    if repeat == "weekly":
        out["weekdays"] = _int_list(reminder.get("weekdays"), 0, 6) or [at.weekday()]
    if repeat == "monthly":
        # 매월 며칠에 울릴지. 31일로 건 알림이 2월(28일)을 지난 뒤에도 다시 31일에 울리도록 따로 적어 둡니다.
        # ("day" 는 날짜를 하나만 고를 수 있던 예전 형식)
        out["days"] = _int_list(reminder.get("days"), 1, 31) or _int_list([reminder.get("day")], 1, 31) or [at.day]
    # 미룬 알림: 미루기 전에 잡혀 있던 다음 정규 시각. 미룬 알림이 울린 뒤 이 시각으로 돌아갑니다.
    resume = _parse_at(reminder.get("resume")) if reminder.get("resume") else None
    if resume is not None and repeat != "none":
        out["resume"] = resume.replace(microsecond=0).isoformat()
    return out


def make(at: datetime, repeat: str = "none", cron: str = "", weekdays: Any = None, days: Any = None) -> Dict[str, Any]:
    """at 에 처음 울리는 새 알림. 크론식이면 at 은 무시하고 지금 이후 첫 시각으로 잡습니다."""
    if repeat not in REPEATS:
        raise ValueError("알 수 없는 반복 방식입니다.")
    if repeat == "cron":
        at = next_cron(cron, datetime.now())
    return normalize({"at": at.isoformat(), "repeat": repeat, "cron": cron.strip(), "weekdays": weekdays, "days": days})


def make_repeating(repeat: str, hour: int, minute: int, now: datetime, weekdays: Any = None, days: Any = None) -> Dict[str, Any]:
    """정한 시각(hour:minute)에 되풀이되는 새 알림. now 이후 처음 돌아오는 때에 처음 울립니다.

    weekly 는 요일(weekdays, 0=월 … 6=일)을, monthly 는 날짜(days, 1~31)를 하나 이상 골라야 합니다.
    """
    if repeat not in ("daily", "weekdays", "weekly", "monthly"):
        raise ValueError("알 수 없는 반복 방식입니다.")
    if repeat == "weekly" and not _int_list(weekdays, 0, 6):
        raise ValueError("알림을 받을 요일을 하나 이상 고르세요.")
    if repeat == "monthly" and not _int_list(days, 1, 31):
        raise ValueError("알림을 받을 날짜를 하나 이상 고르세요.")
    spec = normalize({"at": now.replace(hour=hour, minute=minute, second=0).isoformat(), "repeat": repeat,
                      "weekdays": weekdays, "days": days})
    return {**spec, "at": _next_occurrence(spec, now.replace(microsecond=0)).isoformat()}


def due_at(reminder: Any) -> Optional[datetime]:
    normal = normalize(reminder)
    return _parse_at(normal["at"]) if normal else None


def _day_matches(normal: Dict[str, Any], moment: datetime) -> bool:
    repeat = normal["repeat"]
    if repeat == "weekdays":
        return moment.weekday() < 5
    if repeat == "weekly":
        return moment.weekday() in normal["weekdays"]
    if repeat == "monthly":
        last = calendar.monthrange(moment.year, moment.month)[1]
        return moment.day in {min(day, last) for day in normal["days"]}       # 없는 날짜(31일 등)는 말일로
    return True


def _next_occurrence(normal: Dict[str, Any], after: datetime) -> datetime:
    """after 보다 뒤에 처음 돌아오는 알림 시각. (매일·평일·매주·매월)"""
    at = _parse_at(normal["at"])
    moment = after.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    for _ in range(800):
        if moment > after and _day_matches(normal, moment):
            return moment
        moment += timedelta(days=1)
    raise ValueError("다음 알림 시각을 찾지 못했습니다.")


def following(reminder: Any, now: datetime) -> Optional[Dict[str, Any]]:
    """알림이 울린 뒤의 다음 알림. 한 번만 울리는 알림이면 None.

    앱이 꺼져 있어 여러 번 놓쳤더라도 지나간 것은 건너뛰고 now 이후의 첫 시각으로 잡습니다.
    """
    normal = normalize(reminder)
    if not normal or normal["repeat"] == "none":
        return None
    at = _parse_at(normal["at"])
    repeat = normal["repeat"]
    if normal.get("resume"):
        # 미룬 알림이 울렸으면 원래 정해져 있던 시각으로 돌아갑니다. (미룬 만큼 일정이 밀리지 않게)
        regular = normalize({**normal, "at": normal["resume"], "resume": ""})
        return regular if _parse_at(normal["resume"]) > now else following(regular, now)
    if repeat == "cron":
        nxt = next_cron(normal["cron"], max(now, at))
    else:
        nxt = _next_occurrence(normal, max(now, at))
    return normalize({**normal, "at": nxt.isoformat()})


def upcoming(reminder: Any, count: int = 3) -> List[datetime]:
    """앞으로 울릴 시각을 가까운 것부터 count 개. (한 번만 울리는 알림이면 하나)"""
    out: List[datetime] = []
    current = normalize(reminder)
    while current and len(out) < count:
        moment = _parse_at(current["at"])
        out.append(moment)
        current = following({**current, "resume": ""}, moment)
    return out


def repeat_text(reminder: Any) -> str:
    """반복 방식을 사람이 읽을 말로. 예: '매주 월·수', '매월 1·15일'. 한 번만 울리면 ''."""
    normal = normalize(reminder)
    if not normal or normal["repeat"] == "none":
        return ""
    repeat = normal["repeat"]
    if repeat == "cron":
        return f"크론 {normal['cron']}"
    if repeat == "weekly":
        return "매주 " + "·".join(_WEEKDAYS[d] for d in normal["weekdays"])
    if repeat == "monthly":
        return "매월 " + "·".join(str(d) for d in normal["days"]) + "일"
    return "평일" if repeat == "weekdays" else "매일"


def snoozed(reminder: Any, minutes: int, now: datetime) -> Dict[str, Any]:
    """잠시 뒤 다시 울리도록 미룬 알림.

    reminder 는 지금 메모에 걸려 있는 알림(반복 알림이면 다음 정규 시각)입니다. 반복 알림은 그 시각을
    'resume' 에 적어 두어, 미룬 알림이 울린 뒤 원래 일정으로 돌아가게 합니다.
    """
    normal = normalize(reminder)
    at = (now + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
    if normal and normal["repeat"] != "none":
        return {**normal, "at": at, "resume": normal.get("resume") or normal["at"]}
    return {"at": at, "repeat": "none", "cron": ""}


# 시각을 오전/오후로 나눠 보여 줄지. (환경에 따라 화면 쪽에서 set_ampm 으로 정합니다. 저장되는 값과는 무관)
USE_AMPM = False


def set_ampm(flag: bool) -> None:
    global USE_AMPM
    USE_AMPM = bool(flag)


def clock(moment: datetime) -> str:
    """시각을 글자로. 24시간제 '15:30', 12시간제 '오후 3:30'."""
    if USE_AMPM:
        return f"{'오전' if moment.hour < 12 else '오후'} {moment.hour % 12 or 12}:{moment.minute:02d}"
    return f"{moment.hour:02d}:{moment.minute:02d}"


def describe(reminder: Any) -> str:
    """알림을 사람이 읽을 말로. 예: '10.12(월) 15:00 · 매주 월·수'"""
    normal = normalize(reminder)
    if not normal:
        return ""
    at = _parse_at(normal["at"])
    text = f"{at.month}.{at.day:02d}({_WEEKDAYS[at.weekday()]}) {clock(at)}"
    repeat = repeat_text(normal)
    return f"{text} · {repeat}" if repeat else text
