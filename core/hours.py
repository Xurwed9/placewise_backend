import re
from datetime import datetime, time
from zoneinfo import ZoneInfo


DUSHANBE_TZ = ZoneInfo("Asia/Dushanbe")

DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

DAY_ALIASES = {
    "mon": 0,
    "monday": 0,
    "пн": 0,
    "пон": 0,
    "понедельник": 0,
    "душ": 0,
    "душанбе": 0,
    "tue": 1,
    "tuesday": 1,
    "вт": 1,
    "втор": 1,
    "вторник": 1,
    "сеш": 1,
    "сешанбе": 1,
    "wed": 2,
    "wednesday": 2,
    "ср": 2,
    "среда": 2,
    "чор": 2,
    "чоршанбе": 2,
    "thu": 3,
    "thursday": 3,
    "чт": 3,
    "чет": 3,
    "четверг": 3,
    "панҷ": 3,
    "панҷшанбе": 3,
    "fri": 4,
    "friday": 4,
    "пт": 4,
    "пят": 4,
    "пятница": 4,
    "ҷум": 4,
    "ҷумъа": 4,
    "sat": 5,
    "saturday": 5,
    "сб": 5,
    "суб": 5,
    "суббота": 5,
    "шан": 5,
    "шанбе": 5,
    "sun": 6,
    "sunday": 6,
    "вс": 6,
    "вос": 6,
    "воскресенье": 6,
    "якш": 6,
    "якшанбе": 6,
}

DAY_LABELS = {
    "ru": ("пн", "вт", "ср", "чт", "пт", "сб", "вс"),
    "tg": ("душ", "сеш", "чор", "панҷ", "ҷум", "шан", "якш"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}

DAILY_WORDS = (
    "ежедневно",
    "ежедневный",
    "без выходных",
    "каждый день",
    "ҳар рӯз",
    "хар руз",
    "every day",
    "daily",
)

ROUND_THE_CLOCK_WORDS = (
    "24/7",
    "24 / 7",
    "24 часа",
    "круглосуточно",
    "круглосуточный",
    "шабонарӯз",
    "шабонарӯзӣ",
    "шабонаруз",
    "шабонарузӣ",
)

TIME_RANGE_RE = re.compile(
    r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)\s*-\s*"
    r"([01]?\d|2[0-3]):([0-5]\d)(?!\d)"
)

DAY_RANGE_RE = re.compile(
    r"([A-Za-zА-Яа-яЁёӢӣҲҳҶҷӮӯҒғҚқ]+)"
    r"\s*-\s*"
    r"([A-Za-zА-Яа-яЁёӢӣҲҳҶҷӮӯҒғҚқ]+)"
)

DAY_TOKEN_RE = re.compile(
    r"[A-Za-zА-Яа-яЁёӢӣҲҳҶҷӮӯҒғҚқ]+"
)

DAY_NAMES = {
    "ru": {
        "daily": "ежедневно",
        "closed": "выходной",
        "round_the_clock": "круглосуточно",
    },
    "tg": {
        "daily": "ҳар рӯз",
        "closed": "рӯзи истироҳат",
        "round_the_clock": "шабонарӯзӣ",
    },
    "en": {
        "daily": "daily",
        "closed": "closed",
        "round_the_clock": "24/7",
    },
}


def _clean_text(value):
    text = value.strip().casefold().replace("ё", "е")
    text = (
        text.replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
    )
    text = re.sub(r"\s+", " ", text)
    text = re.sub(
        r"\bс\s+(\d{1,2}:\d{2})\s+до\s+(\d{1,2}:\d{2})",
        r"\1-\2",
        text,
    )
    text = re.sub(
        r"\bfrom\s+(\d{1,2}:\d{2})\s+to\s+(\d{1,2}:\d{2})",
        r"\1-\2",
        text,
    )
    return text


def _has_any(text, words):
    return any(word in text for word in words)


def _day_index(token):
    return DAY_ALIASES.get(token.casefold())


def _parse_day_scope(prefix):
    text = _clean_text(prefix)

    if not text:
        return list(range(7)), False

    if _has_any(text, DAILY_WORDS):
        return list(range(7)), True

    days = set()

    for match in DAY_RANGE_RE.finditer(text):
        start = _day_index(match.group(1))
        end = _day_index(match.group(2))

        if start is None or end is None:
            continue

        if start <= end:
            days.update(range(start, end + 1))
        else:
            days.update(range(start, 7))
            days.update(range(0, end + 1))

    for token in DAY_TOKEN_RE.findall(text):
        day_index = _day_index(token)
        if day_index is not None:
            days.add(day_index)

    if days:
        return sorted(days), True

    return list(range(7)), False


def _normalize_time(value):
    if not isinstance(value, str):
        return None

    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    if hour == 24 and minute == 0:
        return "00:00"
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None

    return f"{hour:02d}:{minute:02d}"


def _normalize_pair(value):
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
    ):
        start = _normalize_time(value[0])
        end = _normalize_time(value[1])
        if start is not None and end is not None:
            return [start, end]

    return None


def _normalize_day(value):
    if value in (None, "", [], {}):
        return []

    if isinstance(value, dict):
        if value.get("closed") is True:
            return []

        start = _normalize_time(value.get("open"))
        end = _normalize_time(value.get("close"))

        if start is not None and end is not None:
            return [start, end]

        return []

    if isinstance(value, str):
        cleaned = _clean_text(value)

        if _has_any(cleaned, ROUND_THE_CLOCK_WORDS):
            return [["00:00", "23:59"]]

        intervals = []
        for match in TIME_RANGE_RE.finditer(cleaned):
            intervals.append([
                f"{int(match.group(1)):02d}:{match.group(2)}",
                f"{int(match.group(3)):02d}:{match.group(4)}",
            ])

        if len(intervals) == 1:
            return intervals[0]

        return intervals

    if not isinstance(value, (list, tuple)):
        return []

    pair = _normalize_pair(value)
    if pair is not None:
        return pair

    intervals = []
    for item in value:
        normalized = _normalize_pair(item)
        if normalized is not None:
            intervals.append(normalized)

    return intervals


def normalize_hours(value):
    if value in (None, "", {}):
        return None

    if isinstance(value, str):
        hours, _ = parse_hours_text(value)
        return hours

    if not isinstance(value, dict):
        return None

    has_day_keys = any(day in value for day in DAY_KEYS)

    if not has_day_keys:
        raw = value.get("raw")

        if isinstance(raw, str) and raw.strip():
            hours, _ = parse_hours_text(raw)
            if hours is not None:
                return hours

        if value.get("closed") is True:
            return {day: [] for day in DAY_KEYS}

        start = _normalize_time(value.get("open"))
        end = _normalize_time(value.get("close"))

        if start is not None and end is not None:
            return {day: [start, end] for day in DAY_KEYS}

        return None

    normalized = {}

    for day in DAY_KEYS:
        if day not in value:
            continue
        normalized[day] = _normalize_day(value[day])

    return normalized or None


def parse_hours_text(raw):
    original = (raw or "").strip()

    if not original:
        return None, []

    text = _clean_text(original)

    if _has_any(text, ROUND_THE_CLOCK_WORDS):
        return "24/7", []

    matches = list(TIME_RANGE_RE.finditer(text))

    if not matches:
        return None, ["Opening hours need manual review"]

    day_intervals = {day: [] for day in DAY_KEYS}
    warnings = []
    previous_scope = None
    cursor = 0

    for match in matches:
        prefix = text[cursor:match.start()]
        cursor = match.end()

        if _has_any(prefix, ("обед", "перерыв", "lunch")):
            warnings.append("Opening hours need manual review")
            continue

        scope, had_day_info = _parse_day_scope(prefix)

        if had_day_info:
            previous_scope = scope
        elif previous_scope is not None:
            scope = previous_scope
        else:
            scope = list(range(7))

        start = f"{int(match.group(1)):02d}:{match.group(2)}"
        end = f"{int(match.group(3)):02d}:{match.group(4)}"

        for day_index in scope:
            day_intervals[DAY_KEYS[day_index]].append([start, end])

    if not any(day_intervals.values()):
        return None, warnings or ["Opening hours need manual review"]

    normalized = {}

    for day, intervals in day_intervals.items():
        if not intervals:
            continue

        if len(intervals) == 1:
            normalized[day] = intervals[0]
        else:
            normalized[day] = intervals

    return normalized, warnings


def _day_pairs(day_value):
    if not day_value:
        return ()

    if (
        isinstance(day_value, (list, tuple))
        and len(day_value) == 2
        and all(isinstance(item, str) for item in day_value)
    ):
        return ((day_value[0], day_value[1]),)

    if not isinstance(day_value, (list, tuple)):
        return ()

    pairs = []
    for item in day_value:
        if (
            isinstance(item, (list, tuple))
            and len(item) == 2
            and all(isinstance(part, str) for part in item)
        ):
            pairs.append((item[0], item[1]))

    return tuple(pairs)


def _time_value(value):
    try:
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def is_open_now(value, now=None):
    hours = normalize_hours(value)

    if hours is None:
        return None

    if hours == "24/7":
        return True

    if now is None:
        now = datetime.now(DUSHANBE_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=DUSHANBE_TZ)
    else:
        now = now.astimezone(DUSHANBE_TZ)

    day_index = now.weekday()
    current = now.time().replace(tzinfo=None)

    previous_index = (day_index - 1) % 7
    previous_pairs = _day_pairs(hours.get(DAY_KEYS[previous_index], []))

    for start_value, end_value in previous_pairs:
        start = _time_value(start_value)
        end = _time_value(end_value)

        if start is None or end is None:
            continue

        if start > end and current < end:
            return True

    today_pairs = _day_pairs(hours.get(DAY_KEYS[day_index], []))

    for start_value, end_value in today_pairs:
        start = _time_value(start_value)
        end = _time_value(end_value)

        if start is None or end is None:
            continue

        if start <= end:
            if start <= current < end:
                return True
        elif current >= start:
            return True

    return False


def _format_intervals(pairs):
    return ", ".join(f"{start}–{end}" for start, end in pairs)


def _format_day_prefix(days, language):
    labels = DAY_LABELS.get(language, DAY_LABELS["ru"])
    daily = DAY_NAMES.get(language, DAY_NAMES["ru"])["daily"]

    if days == list(range(7)):
        return daily

    if len(days) == 1:
        return labels[days[0]]

    is_consecutive = all(
        days[index] + 1 == days[index + 1]
        for index in range(len(days) - 1)
    )

    if is_consecutive:
        return f"{labels[days[0]]}-{labels[days[-1]]}"

    return ", ".join(labels[day] for day in days)


def format_hours_text(value, language="ru"):
    if language not in DAY_NAMES:
        language = "ru"

    hours = normalize_hours(value)

    if hours == "24/7":
        return DAY_NAMES[language]["round_the_clock"]

    if hours is None:
        if isinstance(value, dict):
            raw = value.get("raw")
            if isinstance(raw, str):
                return raw
        if isinstance(value, str):
            return value
        return ""

    grouped = {}

    for day_index, day in enumerate(DAY_KEYS):
        pairs = _day_pairs(hours.get(day, []))
        if not pairs:
            continue
        grouped.setdefault(pairs, []).append(day_index)

    if not grouped:
        return DAY_NAMES[language]["closed"]

    parts = []

    for pairs, days in grouped.items():
        prefix = _format_day_prefix(days, language)
        parts.append(f"{prefix} {_format_intervals(pairs)}")

    return "; ".join(parts)
