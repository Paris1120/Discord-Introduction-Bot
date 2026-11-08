import time

import discord

from config import (AGE_MAX, AGE_MIN, COLOR_BAN, COLOR_ERR, COLOR_INFO, COLOR_KICK, COLOR_LEAVE,
                    COLOR_OK, COLOR_WARN, NAME_MAX, NAME_MIN, ROUTES)
from core.validators import age_bracket


def esc(text) -> str:
    return discord.utils.escape_markdown(discord.utils.escape_mentions(str(text)))


def now_ts() -> int:
    return int(time.time())


MESSAGE_TYPES = {
    "guide": "자기소개 안내 (버튼 메시지)",
    "confirm": "제출 확인 화면",
    "form_error": "입력 오류 안내",
    "already_verified": "이미 인증됨 안내",
    "complete": "인증 완료 안내",
    "welcome_dm": "환영 DM",
    "rejoin_dm": "재입장 복구 DM",
    "unv_warn_dm": "미인증 1차 알림 DM",
    "unv_kick_dm": "미인증 자동 추방 DM",
    "leave_verified": "퇴장 로그 (인증자)",
    "leave_unverified": "퇴장 로그 (미인증자)",
    "leave_autokick": "퇴장 로그 (미인증 자동 추방)",
    "leave_kick": "퇴장 로그 (관리자 추방)",
    "leave_ban": "퇴장 로그 (차단)",
}

MESSAGE_COLORS = {
    "guide": COLOR_INFO, "confirm": COLOR_INFO, "form_error": COLOR_ERR,
    "already_verified": COLOR_WARN, "complete": COLOR_OK, "welcome_dm": COLOR_OK,
    "rejoin_dm": COLOR_OK, "unv_warn_dm": COLOR_WARN, "unv_kick_dm": COLOR_ERR,
    "leave_verified": COLOR_LEAVE, "leave_unverified": COLOR_LEAVE, "leave_autokick": COLOR_WARN,
    "leave_kick": COLOR_KICK, "leave_ban": COLOR_BAN,
}

DEFAULT_MESSAGES = {
    "guide": (
        "{서버}에 오신 걸 환영해요!",
        "아래 **📝 자기소개 작성** 버튼을 눌러 자기소개를 작성하면 자동으로 인증돼요.\n\n"
        "**작성 항목**\n"
        "- **이름**: {이름글자수} (특수문자 가능, 영문, 숫자 불가)\n"
        "- **나이**: {최소나이} ~ {최대나이}\n"
        "- **성별**: 남자 / 여자\n"
        "- **경로**: {경로목록}\n\n"
        "-# 인증은 1회만 가능해요. 정보 수정은 관리자에게 문의해 주세요.",
    ),
    "confirm": (
        "📋 입력 내용 확인",
        "아래 내용으로 제출할까요?\n\n"
        "> **이름**: {이름}\n> **나이**: {나이} ({나이대})\n> **성별**: {성별}\n"
        "> **경로**: {경로}\n> **닉네임**: {닉네임}\n\n"
        "⚠️ 제출 후에는 **직접 수정할 수 없어요.** 잘못 입력했다면 **✏️ 수정**을 눌러주세요.",
    ),
    "form_error": (
        "❌ 입력 오류",
        "{이유}\n\n아래 **✏️ 다시 작성** 버튼을 누르면 입력한 내용이 채워진 상태로 다시 열려요.",
    ),
    "already_verified": (
        "⚠️ 이미 인증된 계정이에요",
        "{유저}님은 이미 자기소개 인증이 완료되었어요.\n정보 수정이 필요하면 **관리자에게 문의**해 주세요.",
    ),
    "complete": (
        "✅ 인증 완료!",
        "{이름}님, 인증이 완료되었어요!\n이제 서버의 채널들을 자유롭게 이용할 수 있어요.",
    ),
    "welcome_dm": (
        "{서버} 인증 완료!",
        "{이름}님, 환영해요! 인증이 완료되었어요.\n\n"
        "### 📜 서버 규칙\n1. 서로 존중해 주세요.\n2. 욕설·비하·도배 금지\n"
        "3. 홍보는 관리자 허락 후 가능\n4. 문제가 생기면 관리자에게 문의해 주세요.",
    ),
    "rejoin_dm": (
        "🔄 다시 오신 걸 환영해요!",
        "{이름}님, **{서버}**에 다시 오셨네요!\n이전 인증 정보와 역할이 자동으로 복구되었어요.",
    ),
    "unv_warn_dm": (
        "⏰ 자기소개 인증 안내",
        "{유저명}님, **{서버}**에서 아직 자기소개 인증을 하지 않으셨어요.\n\n"
        "**{남은시간}** 안에 인증하지 않으면 서버에서 자동으로 내보내져요.\n"
        "자기소개 채널의 **📝 자기소개 작성** 버튼을 눌러주세요!",
    ),
    "unv_kick_dm": (
        "📤 인증 시간 초과",
        "{유저명}님, **{서버}**에서 정해진 시간 안에 인증하지 않아 자동으로 내보내졌어요.\n\n"
        "다시 참여하고 싶다면 아래 링크로 들어와 주세요. (24시간 · 1회용)\n{초대링크}",
    ),
    "leave_verified": ("🚪 퇴장", "{유저} {정보} 님이 퇴장하셨습니다."),
    "leave_unverified": ("🚪 퇴장 (미인증)", "{유저} {정보} 님이 퇴장하셨습니다."),
    "leave_autokick": ("⏰ 미인증 자동 추방", "{유저} {정보} 님이 인증 시간 초과로 자동 추방되었습니다."),
    "leave_kick": (
        "👢 관리자 추방",
        "{유저} {정보} 님이 관리자에 의해 추방되었습니다.\n\n**실행자**: {실행자}\n**사유**: {사유}",
    ),
    "leave_ban": (
        "🔨 차단",
        "{유저} {정보} 님이 서버에서 차단되었습니다.\n\n**실행자**: {실행자}\n**사유**: {사유}",
    ),
}

MESSAGE_PLACEHOLDERS = {
    "guide": ["서버", "이름글자수", "최소나이", "최대나이", "경로목록"],
    "confirm": ["유저", "이름", "나이", "나이대", "성별", "경로", "닉네임"],
    "form_error": ["유저", "이유", "이름글자수", "최소나이", "최대나이", "경로목록"],
    "already_verified": ["유저", "유저명", "서버"],
    "complete": ["유저", "이름", "나이대", "닉네임", "서버"],
    "welcome_dm": ["유저명", "서버", "이름", "나이", "나이대", "성별"],
    "rejoin_dm": ["유저명", "서버", "이름", "닉네임"],
    "unv_warn_dm": ["유저명", "서버", "남은시간"],
    "unv_kick_dm": ["유저명", "서버", "초대링크"],
    "leave_verified": ["유저", "유저명", "정보", "이름", "나이"],
    "leave_unverified": ["유저", "유저명", "정보"],
    "leave_autokick": ["유저", "유저명", "정보"],
    "leave_kick": ["유저", "유저명", "정보", "실행자", "사유"],
    "leave_ban": ["유저", "유저명", "정보", "실행자", "사유"],
}

SAMPLE_DATA = {"name": "홍길동", "age": 20, "gender": "남자", "route": ROUTES[0]}


def fill(text: str, v: dict) -> str:
    for k, val in v.items():
        text = text.replace("{" + k + "}", str(val))
    return text


def tvars(guild: discord.Guild, member: discord.abc.User | None = None,
          data: dict | None = None, **extra) -> dict:
    v = {
        "유저": member.mention if member else "",
        "유저명": esc(member.name) if member else "",
        "서버": esc(guild.name),
        "이름": esc(data["name"]) if data else "",
        "나이": str(data["age"]) if data else "",
        "나이대": age_bracket(data["age"]) if data else "",
        "성별": data["gender"] if data else "",
        "경로": data["route"] if data else "",
        "정보": f"( {esc(data['name'])} / {data['age']} )" if data else "(미인증)",
        "닉네임": "", "이유": "", "남은시간": "", "초대링크": "", "사유": "", "실행자": "",
        "이름글자수": f"{NAME_MIN}~{NAME_MAX}자",
        "최소나이": AGE_MIN, "최대나이": AGE_MAX,
        "경로목록": " / ".join(ROUTES),
    }
    v.update({k: str(val) for k, val in extra.items()})
    return v


def sample_vars(guild: discord.Guild, member: discord.abc.User, prefix: str = "") -> dict:
    return tvars(
        guild, member, SAMPLE_DATA,
        닉네임=esc(f"{prefix}{SAMPLE_DATA['name']}"),
        이유="나이는 **숫자**로 입력해 주세요. (예: 20)",
        남은시간="12시간", 초대링크="https://discord.gg/example",
        사유="(예시) 규칙 위반", 실행자=member.mention,
    )