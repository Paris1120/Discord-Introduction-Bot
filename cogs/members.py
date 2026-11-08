import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from config import AUDIT_LOG_WAIT
from core.messages import esc, now_ts, tvars
from core.ui import as_view, custom_container, dm_card, restore_log_card, send_to
from core.messages import MESSAGE_COLORS, fill
from core.verification import restore_member

log = logging.getLogger("guide-bot.members")


class Members(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── 입장 ──
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        guild = member.guild
        s = await self.bot.db.get_settings(guild.id)
        intro = await self.bot.db.get_latest(guild.id, member.id)

        if intro:  # 재입장 자동 복구
            saved = await self.bot.db.get_saved_roles(guild.id, member.id)
            result = await restore_member(self.bot, member, intro, s, saved)
            await self.bot.db.delete_saved_roles(guild.id, member.id)
            data = dict(intro)
            await send_to(guild, s["log_channel_id"], restore_log_card(member, data, result))
            title, body = await self.bot.db.get_message(guild.id, "rejoin_dm")
            v = tvars(guild, member, data, 닉네임=esc(result["nick"] or data["name"]))
            try:
                await member.send(view=dm_card(fill(title, v), fill(body, v), MESSAGE_COLORS["rejoin_dm"], guild))
            except discord.HTTPException:
                pass
            return

        unv = guild.get_role(s["unverified_role_id"]) if s["unverified_role_id"] else None
        if unv and unv < guild.me.top_role:
            try:
                await member.add_roles(unv, reason="입장 시 미인증 역할 자동 지급")
            except discord.HTTPException as e:
                log.warning(f"[{guild.name}] 미인증 역할 지급 실패: {e}")

    # ── 퇴장 ──
    async def detect_reason(self, member: discord.Member):
        key = (member.guild.id, member.id)
        if key in self.bot.auto_kicked:
            self.bot.auto_kicked.discard(key)
            return "autokick", None, None
        await asyncio.sleep(AUDIT_LOG_WAIT)
        now = datetime.now(timezone.utc)
        try:
            async for entry in member.guild.audit_logs(limit=10):
                if (now - entry.created_at).total_seconds() > 30:
                    break
                if entry.action not in (discord.AuditLogAction.kick, discord.AuditLogAction.ban):
                    continue
                if getattr(entry.target, "id", None) == member.id:
                    kind = "ban" if entry.action == discord.AuditLogAction.ban else "kick"
                    return kind, entry.user, entry.reason
        except discord.HTTPException:
            pass
        return "leave", None, None

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        guild = member.guild
        db = self.bot.db
        reason, executor, audit_reason = await self.detect_reason(member)
        intro = await db.get_latest(guild.id, member.id)
        await db.delete_unv_warn(guild.id, member.id)
        s = await db.get_settings(guild.id)

        if reason in ("kick", "ban"):
            # 관리자 추방/차단 → 기록 삭제 (다시 오면 처음부터 인증)
            await db.delete_user_intros(guild.id, member.id)
            await db.delete_saved_roles(guild.id, member.id)
        elif intro:
            await db.save_roles(guild.id, member.id,
                                [r.id for r in member.roles if not r.is_default() and not r.managed])

        if not s["leave_channel_id"]:
            return
        key = {"autokick": "leave_autokick", "kick": "leave_kick", "ban": "leave_ban"}.get(
            reason, "leave_verified" if intro else "leave_unverified")
        v = tvars(guild, member, dict(intro) if intro else None,
                  실행자=executor.mention if executor else "알 수 없음",
                  사유=esc(audit_reason) if audit_reason else "없음")
        if not intro and s["role_id"] and any(r.id == s["role_id"] for r in member.roles):
            v["정보"] = "(인증 기록 없음)"
        container = await custom_container(
            self.bot, guild, key, v, footer=f"{esc(member.name)} · {member.id} · <t:{now_ts()}:F>")
        await send_to(guild, s["leave_channel_id"], as_view(container))

    # ── 새 채널 자동 잠금 ──
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        s = await self.bot.db.get_settings(channel.guild.id)
        if not s["unv_lock_auto"] or not s["unverified_role_id"] or channel.id == s["intro_channel_id"]:
            return
        role = channel.guild.get_role(s["unverified_role_id"])
        if not role:
            return
        try:
            ow = channel.overwrites_for(role)
            ow.view_channel = False
            await channel.set_permissions(role, overwrite=ow, reason="미인증 잠금 자동 적용")
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(Members(bot))