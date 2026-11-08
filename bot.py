import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from config import COLOR_ERR
from core.database import Database
from core.ui import reply

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
DB_PATH = os.getenv("DB_PATH", "guide_bot.db")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("guide-bot")

EXTENSIONS = [
    "cogs.settings", "cogs.intro", "cogs.members", "cogs.unverified", "cogs.newface",
    "cogs.filter", "cogs.records", "cogs.custom_messages", "cogs.backup",
]


class GuideBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True  # 입장/퇴장, 역할, 닉네임 (Privileged)
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)
        self.db = Database(DB_PATH)
        self.processing: set[tuple[int, int]] = set()   # 인증 처리 중인 유저
        self.auto_kicked: set[tuple[int, int]] = set()  # 봇이 미인증으로 추방한 유저

    async def setup_hook(self):
        await self.db.connect()
        for ext in EXTENSIONS:
            await self.load_extension(ext)
            log.info(f"로드: {ext}")
        self.tree.on_error = on_app_error
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
        else:
            synced = await self.tree.sync()
        log.info(f"슬래시 명령어 {len(synced)}개 동기화 완료")

    async def on_ready(self):
        log.info(f"로그인: {self.user} ({self.user.id}) · 서버 {len(self.guilds)}개")
        await self.change_presence(activity=discord.Game(name="자기소개 확인 중"))

    async def close(self):
        await self.db.close()
        await super().close()


async def on_app_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        title, body = "❌ 권한 부족", "이 명령어는 **서버 관리** 권한이 필요해요."
    elif isinstance(error, app_commands.NoPrivateMessage):
        title, body = "❌ 사용 불가", "서버에서만 사용할 수 있어요."
    else:
        log.exception("명령어 오류", exc_info=error)
        title, body = "❌ 오류 발생", f"```{str(error)[:500]}```"
    try:
        await reply(interaction, title, body, COLOR_ERR)
    except discord.HTTPException:
        pass


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN 이 .env 에 없습니다.")
    GuideBot().run(TOKEN, log_handler=None)