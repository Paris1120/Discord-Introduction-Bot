"""안내봇 공통 기본값. 서버별 설정은 슬래시 명령어로 변경합니다."""
from datetime import time, timedelta, timezone

import discord

KST = timezone(timedelta(hours=9))

# ── 자기소개 검증 ──
NAME_MIN, NAME_MAX = 1, 3
AGE_MIN, AGE_MAX = 12, 39
GENDERS = ["남자", "여자"]
ROUTES = ["지인", "홍보", "기타"]
# 나이대 구간: (라벨, 끝자리 시작, 끝자리 끝)
AGE_SPLITS = [("초반", 0, 3), ("중반", 4, 6), ("후반", 7, 9)]

# ── 금지어 (서버에 처음 쓸 때 자동 등록) ──
DEFAULT_BANNED_WORDS = [
    "관리자", "운영자", "운영진", "서버장", "부서버장", "매니저", "스태프",
    "admin", "staff", "mod", "everyone", "here",
]
# 이 길이 이하의 영어 금지어는 '단어 단위'로만 검사 (mod 때문에 Modric이 막히는 오탐 방지)
SHORT_WORD_LEN = 0

# ── 닉네임 ──
NICK_PREFIX_MAX = 32 - NAME_MAX  # 디스코드 닉네임 32자 제한

# ── 재입장 복구에서 제외할 '관리 권한' ──
DANGEROUS_PERMS = (
    "administrator", "manage_guild", "manage_roles", "manage_channels",
    "kick_members", "ban_members", "moderate_members", "manage_messages",
    "manage_nicknames", "manage_webhooks", "manage_expressions", "manage_events",
    "view_audit_log",
)

# ── 미인증 자동 처리 ──
DEFAULT_UNV_WARN_HOURS = 12
DEFAULT_UNV_KICK_HOURS = 12
UNV_CHECK_MINUTES = 1
UNV_MAX_KICKS_PER_RUN = 10   # 1분에 최대 추방 인원 (레이트리밋 보호)
INVITE_MAX_AGE = 86400       # 재입장 초대 링크 유효시간 (초)

# ── 뉴 페이스 ──
DEFAULT_NEWFACE_DAYS = 7
NEWFACE_CHECK_MINUTES = 10

# ── 기타 ──
DEFAULT_ALT_DAYS = 7
FILTER_LOG_WINDOW = 600      # 같은 유저의 차단 기록을 한 카드에 묶는 시간 (초)
MAIN_CHANNELS_MAX = 8
RECORDS_PER_PAGE = 10
AUDIT_LOG_WAIT = 1.5         # 퇴장 사유 판별 전 감사 로그 대기 (초)

# ── 백업 ──
BACKUP_DIR = "backups"
BACKUP_KEEP = 7
BACKUP_TIME = time(hour=4, minute=0, tzinfo=KST)

# ── 색상 ──
COLOR_OK = discord.Colour.from_rgb(87, 242, 135)
COLOR_ERR = discord.Colour.from_rgb(237, 66, 69)
COLOR_INFO = discord.Colour.from_rgb(88, 101, 242)
COLOR_WARN = discord.Colour.from_rgb(254, 231, 92)
COLOR_LEAVE = discord.Colour.from_rgb(128, 132, 142)
COLOR_KICK = discord.Colour.from_rgb(240, 140, 50)
COLOR_BAN = discord.Colour.from_rgb(150, 20, 30)