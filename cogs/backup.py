import asyncio
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import BACKUP_DIR, BACKUP_KEEP, BACKUP_TIME, COLOR_ERR, KST
from core.ui import admin_command, reply

log = logging.getLogger("guide-bot.backup")


class Backup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.daily.start()

    async def cog_unload(self):
        self.daily.cancel()

    def _backup_sync(self, dst: Path):
        src = sqlite3.connect(self.bot.db.path)
        dest = sqlite3.connect(dst)
        try:
            with dest:
                src.backup(dest)  # 봇 실행 중에도 안전한 SQLite 온라인 백업
        finally:
            dest.close()
            src.close()

    async def make_backup(self) -> Path:
        folder = Path(BACKUP_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        dst = folder / f"guide_bot_{datetime.now(KST):%Y-%m-%d_%H%M%S}.db"
        await asyncio.to_thread(self._backup_sync, dst)
        for old in sorted(folder.glob("guide_bot_*.db"))[:-BACKUP_KEEP]:
            old.unlink(missing_ok=True)
        return dst

    @tasks.loop(time=BACKUP_TIME)
    async def daily(self):
        try:
            path = await self.make_backup()
            log.info(f"자동 백업 완료: {path}")
        except Exception:
            log.exception("자동 백업 실패")

    @app_commands.command(name="백업", description="DB를 즉시 백업합니다.")
    @admin_command()
    async def backup_now(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            path = await self.make_backup()
        except Exception as e:
            log.exception("수동 백업 실패")
            return await reply(interaction, "❌ 백업 실패", f"```{str(e)[:300]}```", COLOR_ERR)
        files = sorted(Path(BACKUP_DIR).glob("guide_bot_*.db"), reverse=True)
        listing = "\n".join(f"- `{f.name}` ({f.stat().st_size / 1024:.1f} KB)" for f in files)
        await reply(interaction, "✅ 백업 완료",
                    f"새 백업: `{path.name}`\n\n**보관 중 ({len(files)}/{BACKUP_KEEP})**\n{listing}\n\n"
                    f"-# 매일 {BACKUP_TIME.strftime('%H:%M')} (KST) 자동 백업")


async def setup(bot):
    await bot.add_cog(Backup(bot))