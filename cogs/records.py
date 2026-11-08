from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from config import AGE_MAX, AGE_MIN, COLOR_ERR, COLOR_OK, COLOR_WARN, GENDERS, NAME_MAX, ROUTES
from core.messages import esc
from core.ui import NO_MENTIONS, PagedView, admin_command, intro_log_card, reply, send_to
from core.validators import age_bracket, validate_name
from core.verification import apply_verification, remove_verification

GENDER_CHOICES = [app_commands.Choice(name=g, value=g) for g in GENDERS]
ROUTE_CHOICES = [app_commands.Choice(name=r, value=r) for r in ROUTES]


class Records(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="안내기록", description="인증된 자기소개를 최신순으로 보여줍니다. (중복 제외)")
    @admin_command()
    async def records(self, interaction: discord.Interaction):
        guild = interaction.guild
        s = await self.bot.db.get_settings(guild.id)
        if not s["admin_channel_id"]:
            return await reply(interaction, "❌ 사용 불가", "먼저 `/관리자채널` 을 설정해 주세요.", COLOR_ERR)
        if interaction.channel_id != s["admin_channel_id"]:
            return await reply(interaction, "❌ 사용 불가",
                               f"이 명령어는 <#{s['admin_channel_id']}> 에서만 사용할 수 있어요.", COLOR_ERR)

        rows = await self.bot.db.get_records(guild.id)
        lines = []
        for i, r in enumerate(rows, 1):
            ts = int(datetime.fromisoformat(r["created_at"]).timestamp())
            left = "" if guild.get_member(r["user_id"]) else " · 🚪 퇴장"
            lines.append(f"**{i}.** {esc(r['name'])} / {r['age']} / {r['gender']} / {r['route']}\n"
                         f"-# <@{r['user_id']}> · {age_bracket(r['age'])} · <t:{ts}:R>{left}")
        male = sum(1 for r in rows if r["gender"] == "남자")
        routes = " · ".join(f"{rt} {sum(1 for r in rows if r['route'] == rt)}" for rt in ROUTES)
        view = PagedView(f"📋 안내 기록 · 총 {len(rows)}명", lines,
                         subtitle=f"남자 {male} · 여자 {len(rows) - male} | {routes}",
                         note="중복 제외 · 최신순", empty="아직 기록이 없어요.")
        await interaction.response.send_message(view=view, allowed_mentions=NO_MENTIONS)
        view.sent_message = await interaction.original_response()

    @app_commands.command(name="인증수정", description="[관리자] 유저의 자기소개 정보를 수정하고 역할/닉네임을 다시 적용합니다.")
    @app_commands.describe(유저="대상 유저", 이름="이름", 나이="나이", 성별="성별", 경로="경로")
    @app_commands.choices(성별=GENDER_CHOICES, 경로=ROUTE_CHOICES)
    @admin_command()
    async def edit(self, interaction: discord.Interaction, 유저: discord.Member,
                   이름: app_commands.Range[str, 1, NAME_MAX],
                   나이: app_commands.Range[int, AGE_MIN, AGE_MAX], 성별: str, 경로: str):
        name = 이름.strip()
        err, _, _ = validate_name(name, [])  # 관리자는 금지어 검사 생략
        if err:
            return await reply(interaction, "❌ 수정 실패", err, COLOR_ERR)
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        s = await self.bot.db.get_settings(guild.id)
        latest = await self.bot.db.get_latest(guild.id, 유저.id)

        # 기존 접두사/뉴페이스 상태/인증 시각 유지
        if latest:
            prefix, removed, created = latest["prefix"] or "", bool(latest["prefix_removed"]), latest["created_at"]
        else:
            prefix, removed, created = s["nick_prefix"], False, None
        data = {"name": name, "age": 나이, "gender": 성별, "route": 경로}
        await self.bot.db.add_intro(guild.id, 유저.id, data, prefix, removed, created)
        await self.bot.db.delete_unv_warn(guild.id, 유저.id)
        warnings, nick = await apply_verification(self.bot, 유저, data, s, "" if removed else prefix)

        await send_to(guild, s["log_channel_id"],
                      intro_log_card(유저, data, warnings, nick, s, edited_by=interaction.user))
        body = f"{유저.mention} → **{esc(name)} / {나이} / {성별} / {경로}** ({age_bracket(나이)})"
        if warnings:
            body += "\n\n" + "\n".join(f"⚠️ {w}" for w in warnings)
        await reply(interaction, "✅ 인증 정보 수정", body, COLOR_WARN if warnings else COLOR_OK)

    @app_commands.command(name="인증해제", description="[관리자] 유저의 인증을 해제합니다. (기록 삭제, 다시 작성 가능)")
    @admin_command()
    async def unverify(self, interaction: discord.Interaction, 유저: discord.Member):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        s = await self.bot.db.get_settings(guild.id)
        warnings = await remove_verification(self.bot, 유저, s)
        await self.bot.db.delete_user_intros(guild.id, 유저.id)
        await self.bot.db.delete_saved_roles(guild.id, 유저.id)
        body = f"{유저.mention} 의 인증을 해제했어요. 이제 다시 자기소개를 작성할 수 있어요."
        if warnings:
            body += "\n\n" + "\n".join(f"⚠️ {w}" for w in warnings)
        await reply(interaction, "✅ 인증 해제", body, COLOR_WARN if warnings else COLOR_OK)


async def setup(bot):
    await bot.add_cog(Records(bot))