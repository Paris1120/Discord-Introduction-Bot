import re
import unicodedata

from config import AGE_MAX, AGE_MIN, AGE_SPLITS, GENDERS, NAME_MAX, NAME_MIN, ROUTES, SHORT_WORD_LEN

JAMO = re.compile(r"[ㄱ-ㅎㅏ-ㅣ]")
REPEAT = re.compile(r"(.)\1{3,}")
LINK = re.compile(r"(https?://|www\.|discord\.gg|<[@#&:!]|@everyone|@here)", re.I)
LETTER = re.compile(r"[가-힣a-zA-Z]")

CATEGORY_LABELS = {"format": "양식 오류", "prank": "장난 입력", "banned": "금지어"}


def normalize(text: str) -> str:
    """금지어 비교용: 전각→반각, 소문자, 공백/특수문자 제거"""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^가-힣ㄱ-ㅎㅏ-ㅣa-z0-9]", "", text)


def _tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    return set(re.findall(r"[가-힣a-z0-9]+", text))


def find_banned(name: str, words: list[str]) -> str | None:
    norm, toks = normalize(name), _tokens(name)
    for w in words:
        if not w:
            continue
        if w.isascii() and len(w) <= SHORT_WORD_LEN:
            if w == norm or w in toks:
                return w
        elif w in norm:
            return w
    return None


def validate_name(name: str, banned: list[str]) -> tuple[str | None, str | None, str | None]:
    """반환: (오류 메시지, 분류, 걸린 금지어)"""
    if not (NAME_MIN <= len(name) <= NAME_MAX):
        return f"이름은 **{NAME_MIN}~{NAME_MAX}자**로 입력해 주세요.", "format", None
    if re.search(r"\d", name):
        return "이름에 **숫자**는 사용할 수 없어요.", "format", None
    if not LETTER.search(name):
        return "이름에 **한글 또는 영문**이 최소 1자 포함되어야 해요.", "format", None
    if JAMO.search(name):
        return "자음/모음만 따로 쓰는 이름은 사용할 수 없어요.", "prank", None
    if REPEAT.search(name.replace(" ", "")):
        return "같은 글자를 반복하는 이름은 사용할 수 없어요.", "prank", None
    if LINK.search(name):
        return "이름에 링크나 멘션은 사용할 수 없어요.", "prank", None
    if matched := find_banned(name, banned):
        return "사용할 수 없는 이름이에요. 다른 이름으로 입력해 주세요.", "banned", matched
    return None, None, None


def validate_age(raw: str) -> tuple[int | None, str | None]:
    s = unicodedata.normalize("NFKC", raw).strip()
    s = re.sub(r"\s*(살|세)$", "", s)
    if not re.fullmatch(r"[0-9]{1,3}", s):
        return None, "나이는 **숫자**로 입력해 주세요. (예: 20)"
    age = int(s)
    if not (AGE_MIN <= age <= AGE_MAX):
        return None, f"나이는 **{AGE_MIN}~{AGE_MAX}** 사이로 입력해 주세요."
    return age, None


def validate_intro(raw: dict, banned: list[str]):
    """반환: (data, 오류, 분류, 걸린 금지어)"""
    name = raw.get("name", "").strip()
    err, cat, matched = validate_name(name, banned)
    if err:
        return None, err, cat, matched
    age, err = validate_age(raw.get("age", ""))
    if err:
        return None, err, "format", None
    if raw.get("gender") not in GENDERS:
        return None, "성별을 선택해 주세요.", "format", None
    if raw.get("route") not in ROUTES:
        return None, "경로를 선택해 주세요.", "format", None
    return {"name": name, "age": age, "gender": raw["gender"], "route": raw["route"]}, None, None, None


def age_bracket(age: int) -> str:
    decade, r = (age // 10) * 10, age % 10
    for label, lo, hi in AGE_SPLITS:
        if lo <= r <= hi:
            return f"{decade}대 {label}"
    return f"{decade}대"


def all_brackets() -> list[tuple[str, int, int]]:
    out = []
    for decade in range((AGE_MIN // 10) * 10, AGE_MAX + 1, 10):
        for label, lo, hi in AGE_SPLITS:
            a, b = max(decade + lo, AGE_MIN), min(decade + hi, AGE_MAX)
            if a <= b:
                out.append((f"{decade}대 {label}", a, b))
    return out


BRACKETS = all_brackets()