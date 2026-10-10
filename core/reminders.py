"""메모 알림.

메모의 'reminder' 값 하나로 표현합니다.
    {"at": "2026-10-12T15:00:00", "repeat": "none", "cron": ""}
 - at     : 다음에 울릴 시각 (그 PC의 지역 시각)
 - repeat : "none"(한 번) / "daily"(매일) / "weekdays"(평일마다) / "weekly"(매주) / "monthly"(매월) / "cron"(크론식)
 - cron   : repeat 가 "cron" 일 때의 크론식. "분 시 일 월 요일" 다섯 칸.

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
    if repeat == "monthly":
        # 매월 며칠에 울릴지. 31일로 건 알림이 2월(28일)을 지난 뒤에도 다시 31일에 울리도록 따로 적어 둡니다.
        day = reminder.get("day")
        out["day"] = day if isinstance(day, int) and not isinstance(day, bool) and 1 <= day <= 31 else at.day
    # 미룬 알림: 미루기 전에 잡혀 있던 다음 정규 시각. 미룬 알림이 울린 뒤 이 시각으로 돌아갑니다.
    resume = _parse_at(reminder.get("resume")) if reminder.get("resume") else None
    if resume is not None and repeat != "none":
        out["resume"] = resume.replace(microsecond=0).isoformat()
    return out


def make(at: datetime, repeat: str = "none", cron: str = "") -> Dict[str, Any]:
    """새 알림. 크론식이면 at 은 무시하고 지금 이후 첫 시각으로 잡습니다."""
    if repeat not in REPEATS:
        raise ValueError("알 수 없는 반복 방식입니다.")
    if repeat == "cron":
        at = next_cron(cron, datetime.now())
    return normalize({"at": at.isoformat(), "repeat": repeat, "cron": cron.strip()})


def due_at(reminder: Any) -> Optional[datetime]:
    normal = normalize(reminder)
    return _parse_at(normal["at"]) if normal else None


def _add_months(moment: datetime, months: int, day: int) -> datetime:
    """months 달 뒤의 day 일. 그 달에 day 일이 없으면 그 달의 마지막 날."""
    index = moment.month - 1 + months
    year, month = moment.year + index // 12, index % 12 + 1
    return moment.replace(year=year, month=month, day=min(day, calendar.monthrange(year, month)[1]))


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
    elif repeat == "monthly":
        step, nxt = 1, _add_months(at, 1, normal["day"])
        while nxt <= now:
            step += 1
            nxt = _add_months(at, step, normal["day"])
    else:
        days = 7 if repeat == "weekly" else 1
        nxt = at + timedelta(days=days)
        if nxt <= now:
            behind = (now - nxt).days // days + 1
            nxt += timedelta(days=days * behind)
        while repeat == "weekdays" and nxt.weekday() >= 5:
            nxt += timedelta(days=1)
    return normalize({**normal, "at": nxt.isoformat()})


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


def describe(reminder: Any) -> str:
    """알림을 사람이 읽을 말로. 예: '10.12(월) 15:00 · 매주'"""
    normal = normalize(reminder)
    if not normal:
        return ""
    at = _parse_at(normal["at"])
    text = f"{at.month}.{at.day:02d}({_WEEKDAYS[at.weekday()]}) {at.hour:02d}:{at.minute:02d}"
    if normal["repeat"] == "cron":
        return f"{text} · 크론 {normal['cron']}"
    if normal["repeat"] != "none":
        return f"{text} · {REPEAT_LABELS[normal['repeat']].split(' (')[0]}"
    return text
