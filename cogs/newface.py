import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import NEWFACE_CHECK_MINUTES
from core.messages import esc
from core.ui import ONOFF, admin_command, reply

log = logging.getLogger("guide-bot.newface")


class NewFace(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.checker.start()

    async def cog_unload(self):
        self.checker.cancel()

    @app_commands.command(name="뉴페이스자동제거", description="인증 후 N일이 지나면 닉네임 접두사를 자동으로 뗍니다.")
    @app_commands.describe(상태="켜기/끄기", 일수="인증 후 며칠 뒤에 뗄지 (기본 7)")
    @app_commands.choices(상태=ONOFF)
    @admin_command()
    async def toggle(self, interaction: discord.Interaction, 상태: str,
                     일수: app_commands.Range[int, 1, 365] | None = None):
        values = {"newface_enabled": 1 if 상태 == "on" else 0}
        if 일수:
            values["newface_days"] = 일수
        await self.bot.db.set_settings(interaction.guild.id, **values)
        s = await self.bot.db.get_settings(interaction.guild.id)
        await reply(interaction, "✅ 뉴 페이스 자동 제거",
                    f"상태: **{'켜짐' if s['newface_enabled'] else '꺼짐'}**\n"
                    f"인증 후 **{s['newface_days']}일**이 지나면 `{esc(s['nick_prefix']) or '(접두사)'}` 를 떼고 이름만 남겨요.")

    @tasks.loop(minutes=NEWFACE_CHECK_MINUTES)
    async def checker(self):
        for guild in self.bot.guilds:
            try:
                await self.process_guild(guild)
            except Exception:
                log.exception(f"[{guild.name}] 뉴 페이스 처리 오류")

    @checker.before_loop
    async def before_checker(self):
        await self.bot.wait_until_ready()

    async def process_guild(self, guild: discord.Guild):
        s = await self.bot.db.get_settings(guild.id)
        if not s["newface_enabled"]:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=s["newface_days"])
        for row in await self.bot.db.get_records(guild.id):
            prefix = row["prefix"] or ""
            if not prefix or row["prefix_removed"]:
                continue
            if datetime.fromisoformat(row["created_at"]) > cutoff:
                continue
            member = guild.get_member(row["user_id"])
            if member and member.nick and member.nick.startswith(prefix):
                new_nick = member.nick[len(prefix):].strip() or row["name"]
                try:
                    await member.edit(nick=new_nick, reason="뉴 페이스 기간 종료")
                except discord.Forbidden:
                    pass  # 권한 문제는 재시도해도 실패하므로 처리 완료로 표시
                except discord.HTTPException:
                    continue  # 일시적 오류 → 다음 주기에 재시도
            await self.bot.db.mark_prefix_removed(row["id"])


async def setup(bot):
    await bot.add_cog(NewFace(bot))