import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import COLOR_ERR, COLOR_INFO, COLOR_OK, COLOR_WARN, INVITE_MAX_AGE, UNV_CHECK_MINUTES, UNV_MAX_KICKS_PER_RUN
from core.messages import MESSAGE_COLORS, fill, tvars
from core.ui import dm_card, reply

log = logging.getLogger("guide-bot.unverified")


class Unverified(commands.Cog):
    group = app_commands.Group(
        name="미인증처리", description="미인증 유저 자동 알림/추방 설정",
        guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.checker.start()

    async def cog_unload(self):
        self.checker.cancel()

    # ── 대상자 판별 ──
    @staticmethod
    def candidates(guild: discord.Guild, s: dict, exempt: set[int]):
        since = s["unv_since"]
        for m in guild.members:
            if m.bot or m.guild_permissions.manage_guild:
                continue
            if any(r.id == s["role_id"] for r in m.roles):
                continue
            if exempt and any(r.id in exempt for r in m.roles):
                continue
            if m.joined_at is None or m.joined_at.timestamp() < since:
                continue  # 기능 켜기 전에 있던 유저 제외
            yield m

    # ── 스케줄러 ──
    @tasks.loop(minutes=UNV_CHECK_MINUTES)
    async def checker(self):
        for guild in self.bot.guilds:
            try:
                await self.process_guild(guild)
            except Exception:
                log.exception(f"[{guild.name}] 미인증 처리 오류")

    @checker.before_loop
    async def before_checker(self):
        await self.bot.wait_until_ready()

    async def process_guild(self, guild: discord.Guild):
        db = self.bot.db
        s = await db.get_settings(guild.id)
        if not s["unv_enabled"] or not s["unv_since"] or not s["role_id"]:
            return
        exempt = set(await db.get_exempt_roles(guild.id))
        warns = await db.get_unv_warns(guild.id)
        now = time.time()
        kicks = 0
        for m in self.candidates(guild, s, exempt):
            if (guild.id, m.id) in self.bot.processing:
                continue
            warned = warns.get(m.id)
            if warned is None:
                if now - m.joined_at.timestamp() >= s["unv_warn_hours"] * 3600:
                    await self.warn(guild, m, s)
                    await db.set_unv_warn(guild.id, m.id, int(now))
            elif now - warned >= s["unv_kick_hours"] * 3600 and kicks < UNV_MAX_KICKS_PER_RUN:
                if await self.kick(guild, m, s):
                    kicks += 1

    async def warn(self, guild: discord.Guild, member: discord.Member, s: dict):
        title, body = await self.bot.db.get_message(guild.id, "unv_warn_dm")
        v = tvars(guild, member, 남은시간=f"{s['unv_kick_hours']}시간")
        ch = guild.get_channel(s["intro_channel_id"]) if s["intro_channel_id"] else None
        try:
            await member.send(view=dm_card(fill(title, v), fill(body, v), MESSAGE_COLORS["unv_warn_dm"], guild,
                                           link_label="자기소개 채널로 이동", link_url=ch.jump_url if ch else None))
        except discord.HTTPException:
            pass

    async def kick(self, guild: discord.Guild, member: discord.Member, s: dict) -> bool:
        invite_url = None
        ch = guild.get_channel(s["intro_channel_id"]) if s["intro_channel_id"] else guild.system_channel
        if ch:
            try:
                inv = await ch.create_invite(max_age=INVITE_MAX_AGE, max_uses=1, unique=True,
                                             reason="미인증 자동 추방 재입장 링크")
                invite_url = inv.url
            except discord.HTTPException:
                pass
        title, body = await self.bot.db.get_message(guild.id, "unv_kick_dm")
        v = tvars(guild, member, 초대링크=invite_url or "(초대 링크를 만들지 못했어요. 관리자에게 문의해 주세요.)")
        try:
            await member.send(view=dm_card(fill(title, v), fill(body, v), MESSAGE_COLORS["unv_kick_dm"], guild,
                                           link_label="다시 참여하기", link_url=invite_url))
        except discord.HTTPException:
            pass

        key = (guild.id, member.id)
        self.bot.auto_kicked.add(key)
        try:
            await member.kick(reason=f"미인증 자동 추방 (입장 후 {s['unv_warn_hours'] + s['unv_kick_hours']}시간)")
        except discord.HTTPException as e:
            self.bot.auto_kicked.discard(key)
            log.warning(f"[{guild.name}] {member} 추방 실패: {e}")
            return False
        await self.bot.db.delete_unv_warn(guild.id, member.id)
        return True

    # ── 명령어 ──
    @group.command(name="켜기", description="미인증 자동 처리를 켭니다. (지금 이후 입장한 사람부터 적용)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def turn_on(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        s = await self.bot.db.get_settings(gid)
        if not s["role_id"]:
            return await reply(interaction, "❌ 켜기 실패", "먼저 `/인증역할` 을 설정해 주세요.", COLOR_ERR)
        if s["unv_enabled"]:
            return await reply(interaction, "ℹ️ 이미 켜져 있어요",
                               f"<t:{s['unv_since']}:F> 이후 입장한 유저에게 적용 중이에요.", COLOR_INFO)
        now = int(time.time())
        await self.bot.db.set_settings(gid, unv_enabled=1, unv_since=now)
        tip = "" if s["unverified_role_id"] else "\n\n-# 💡 `/미인증역할` 을 설정하면 입장 즉시 미인증 역할이 지급돼요."
        await reply(interaction, "✅ 미인증 자동 처리 켜짐",
                    f"**<t:{now}:F> 이후 입장한 미인증 유저**부터 적용돼요. 기존 유저는 제외돼요.\n\n"
                    f"⏰ 입장 **{s['unv_warn_hours']}시간** 후 1차 DM 알림\n"
                    f"👢 알림 **{s['unv_kick_hours']}시간** 후에도 미인증이면 추방{tip}", COLOR_OK)

    @group.command(name="끄기", description="미인증 자동 처리를 끕니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def turn_off(self, interaction: discord.Interaction):
        await self.bot.db.set_settings(interaction.guild.id, unv_enabled=0)
        await self.bot.db.clear_unv_warns(interaction.guild.id)
        await reply(interaction, "✅ 미인증 자동 처리 꺼짐",
                    "다시 켜면 **켠 시점 이후** 입장한 사람부터 새로 적용돼요.", COLOR_OK)

    @group.command(name="시간", description="알림/추방까지 걸리는 시간을 설정합니다.")
    @app_commands.describe(알림시간="입장 후 몇 시간 뒤 1차 알림", 추방시간="알림 후 몇 시간 뒤 추방")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_hours(self, interaction: discord.Interaction,
                        알림시간: app_commands.Range[int, 1, 168], 추방시간: app_commands.Range[int, 1, 168]):
        await self.bot.db.set_settings(interaction.guild.id, unv_warn_hours=알림시간, unv_kick_hours=추방시간)
        await reply(interaction, "✅ 시간 설정",
                    f"⏰ 1차 알림: 입장 후 **{알림시간}시간**\n👢 추방: 알림 후 **{추방시간}시간** (입장 후 총 {알림시간 + 추방시간}시간)")

    @group.command(name="예외추가", description="자동 처리에서 제외할 역할을 추가합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add_exempt(self, interaction: discord.Interaction, 역할: discord.Role):
        await self.bot.db.add_exempt_role(interaction.guild.id, 역할.id)
        await reply(interaction, "✅ 예외 역할 추가", f"{역할.mention} 을(를) 가진 유저는 자동 처리에서 제외돼요.")

    @group.command(name="예외삭제", description="예외 역할을 삭제합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove_exempt(self, interaction: discord.Interaction, 역할: discord.Role):
        ok = await self.bot.db.remove_exempt_role(interaction.guild.id, 역할.id)
        await reply(interaction, "✅ 삭제 완료" if ok else "❌ 없음",
                    f"{역할.mention} {'을(를) 예외에서 삭제했어요.' if ok else '은(는) 예외 역할이 아니에요.'}",
                    COLOR_OK if ok else COLOR_ERR)

    @group.command(name="상태", description="미인증 자동 처리 현황을 확인합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction):
        guild = interaction.guild
        s = await self.bot.db.get_settings(guild.id)
        exempt = await self.bot.db.get_exempt_roles(guild.id)
        lines = [f"상태: **{'켜짐' if s['unv_enabled'] else '꺼짐'}**",
                 f"⏰ 알림 {s['unv_warn_hours']}시간 → 👢 추방 {s['unv_kick_hours']}시간",
                 f"🛡️ 예외 역할: {', '.join(f'<@&{r}>' for r in exempt) or '없음'}"]
        if s["unv_enabled"] and s["unv_since"] and s["role_id"]:
            warns = await self.bot.db.get_unv_warns(guild.id)
            targets = list(self.candidates(guild, s, set(exempt)))
            warned = sum(1 for m in targets if m.id in warns)
            lines += [f"📅 적용 기준: <t:{s['unv_since']}:F> 이후 입장",
                      f"👥 현재 대상: **{len(targets)}명** (알림 보냄 {warned}명 · 대기 {len(targets) - warned}명)"]
        await reply(interaction, "📊 미인증 자동 처리", "\n".join(lines),
                    COLOR_INFO if s["unv_enabled"] else COLOR_WARN)


async def setup(bot):
    await bot.add_cog(Unverified(bot))