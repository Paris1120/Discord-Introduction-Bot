from datetime import datetime, timedelta, timezone

import discord

from config import DANGEROUS_PERMS
from core.messages import esc
from core.validators import age_bracket


def is_dangerous(role: discord.Role) -> bool:
    p = role.permissions
    return any(getattr(p, name, False) for name in DANGEROUS_PERMS)


def check_role(role: discord.Role, guild: discord.Guild) -> str | None:
    if role.is_default() or role.managed:
        return f"{role.mention} 은(는) 지급/제거할 수 없는 역할이에요."
    if role >= guild.me.top_role:
        return (f"{role.mention} 이(가) 봇 역할보다 높거나 같아요.\n"
                f"서버 설정 → 역할에서 **봇 역할을 더 위로** 올려주세요.")
    return None


def build_nick(prefix: str, name: str) -> str:
    return f"{prefix}{name}"[:32]


async def is_verified(bot, member: discord.Member, s: dict) -> bool:
    if s["role_id"]:
        return any(r.id == s["role_id"] for r in member.roles)
    return await bot.db.get_latest(member.guild.id, member.id) is not None


async def verification_role_ids(bot, guild: discord.Guild, data: dict, s: dict) -> tuple[set[int], set[int]]:
    add, remove = set(), set()
    if s["role_id"]:
        add.add(s["role_id"])
    if s["unverified_role_id"]:
        remove.add(s["unverified_role_id"])
    for gender, key in (("남자", "male_role_id"), ("여자", "female_role_id")):
        if s[key]:
            (add if data["gender"] == gender else remove).add(s[key])
    bracket = age_bracket(data["age"])
    for b, rid in (await bot.db.get_age_roles(guild.id)).items():
        (add if b == bracket else remove).add(rid)
    return add, remove - add


async def edit_roles(member: discord.Member, add_ids: set[int], remove_ids: set[int], reason: str) -> list[str]:
    guild, top = member.guild, member.guild.me.top_role
    current = {r.id for r in member.roles}
    warnings, to_add, to_remove, blocked = [], [], [], []

    for ids, bucket, want_present in ((add_ids, to_add, False), (remove_ids, to_remove, True)):
        for rid in ids:
            if (rid in current) != want_present:
                continue
            role = guild.get_role(rid)
            if role is None:
                continue
            if role >= top or role.managed:
                blocked.append(role)
            else:
                bucket.append(role)

    if blocked:
        warnings.append("봇보다 높은 역할이라 처리 불가: " + ", ".join(r.mention for r in blocked))
    if to_add:
        try:
            await member.add_roles(*to_add, reason=reason)
        except discord.HTTPException:
            warnings.append("역할 지급 실패 (봇 권한/역할 순서 확인)")
    if to_remove:
        try:
            await member.remove_roles(*to_remove, reason=reason)
        except discord.HTTPException:
            warnings.append("역할 제거 실패 (봇 권한/역할 순서 확인)")
    return warnings


async def set_nick(member: discord.Member, nick: str | None, reason: str) -> tuple[str | None, str | None]:
    guild = member.guild
    if member.id == guild.owner_id:
        return None, "서버장은 닉네임을 변경할 수 없음"
    if member.top_role >= guild.me.top_role:
        return None, "봇보다 높은 역할이라 닉네임 변경 불가"
    try:
        await member.edit(nick=nick, reason=reason)
        return nick, None
    except discord.HTTPException:
        return None, "닉네임 변경 실패"


async def apply_verification(bot, member: discord.Member, data: dict, s: dict, prefix: str):
    warnings = []
    if not s["role_id"]:
        warnings.append("인증 역할이 설정되지 않음 (`/인증역할`)")
    add, remove = await verification_role_ids(bot, member.guild, data, s)
    warnings += await edit_roles(member, add, remove, "자기소개 인증")
    nick, w = await set_nick(member, build_nick(prefix, data["name"]), "자기소개 인증 닉네임")
    if w:
        warnings.append(w)
    return warnings, nick


async def remove_verification(bot, member: discord.Member, s: dict) -> list[str]:
    ids = {s["role_id"], s["male_role_id"], s["female_role_id"]}
    ids |= set((await bot.db.get_age_roles(member.guild.id)).values())
    ids.discard(None)
    add = {s["unverified_role_id"]} if s["unverified_role_id"] else set()
    warnings = await edit_roles(member, add, ids, "관리자 인증 해제")
    _, w = await set_nick(member, None, "관리자 인증 해제")
    if w:
        warnings.append(w)
    return warnings


def effective_prefix(intro, s: dict) -> tuple[str, bool]:
    """반환: (복구할 접두사, 뉴페이스 기간 만료 여부)"""
    prefix = intro["prefix"] or ""
    if not prefix or intro["prefix_removed"]:
        return "", False
    if s["newface_enabled"]:
        created = datetime.fromisoformat(intro["created_at"])
        if datetime.now(timezone.utc) - created >= timedelta(days=s["newface_days"]):
            return "", True
    return prefix, False


async def restore_member(bot, member: discord.Member, intro, s: dict, saved_ids: list[int]) -> dict:
    guild, top = member.guild, member.guild.me.top_role
    data = dict(intro)
    add_ids, _ = await verification_role_ids(bot, guild, data, s)
    ids = set(saved_ids) | add_ids
    ids.discard(s["unverified_role_id"])

    restored, danger, high, missing = [], [], [], 0
    for rid in ids:
        role = guild.get_role(rid)
        if role is None:
            missing += 1
            continue
        if role.is_default() or role.managed or role in member.roles:
            continue
        if is_dangerous(role):
            danger.append(role)
        elif role >= top:
            high.append(role)
        else:
            restored.append(role)

    warnings = []
    if restored:
        try:
            await member.add_roles(*restored, reason="재입장 자동 복구")
        except discord.HTTPException:
            warnings.append("역할 복구 실패")
            restored = []
    unv = guild.get_role(s["unverified_role_id"]) if s["unverified_role_id"] else None
    if unv and unv in member.roles and unv < top:
        try:
            await member.remove_roles(unv, reason="재입장 자동 복구")
        except discord.HTTPException:
            pass

    prefix, expired = effective_prefix(intro, s)
    if expired:
        await bot.db.mark_prefix_removed(intro["id"])
    nick, w = await set_nick(member, build_nick(prefix, intro["name"]), "재입장 자동 복구")
    if w:
        warnings.append(w)
    return {"restored": restored, "danger": danger, "high": high,
            "missing": missing, "nick": nick, "warnings": warnings}


async def lock_intro_channel(guild: discord.Guild, s: dict) -> str:
    """자기소개 채널: 채팅 잠금 (버튼으로만 작성), 미인증 역할 보기 허용"""
    ch = guild.get_channel(s["intro_channel_id"]) if s["intro_channel_id"] else None
    if not isinstance(ch, discord.TextChannel):
        return "-# 자기소개 채널이 설정되면 채팅 잠금이 자동 적용돼요."
    lines = []
    try:
        ow = ch.overwrites_for(guild.default_role)
        ow.update(send_messages=False, add_reactions=False, create_public_threads=False,
                  create_private_threads=False, send_messages_in_threads=False)
        await ch.set_permissions(guild.default_role, overwrite=ow, reason="자기소개 채널 채팅 잠금")
        lines.append(f"🔒 {ch.mention} 채팅 잠금 완료 (버튼으로만 작성)")
    except discord.HTTPException:
        lines.append(f"⚠️ {ch.mention} 채팅 잠금 실패")
    unv = guild.get_role(s["unverified_role_id"]) if s["unverified_role_id"] else None
    if unv:
        try:
            ow = ch.overwrites_for(unv)
            ow.update(view_channel=True, read_message_history=True, send_messages=False)
            await ch.set_permissions(unv, overwrite=ow, reason="미인증 역할 자기소개 채널 허용")
            lines.append(f"👀 {unv.mention} 은(는) {ch.mention} 을(를) 볼 수 있어요.")
        except discord.HTTPException:
            lines.append(f"⚠️ {esc(unv.name)} 권한 설정 실패")
    return "\n".join(lines)