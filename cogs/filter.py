import time

import discord
from discord import app_commands
from discord.ext import commands

from config import COLOR_ERR, COLOR_WARN, FILTER_LOG_WINDOW
from core.messages import esc, now_ts
from core.ui import NO_MENTIONS, PagedView, as_view, reply
from core.validators import CATEGORY_LABELS, normalize


class Filter(commands.Cog):
    group = app_commands.Group(
        name="금지어", description="자기소개 이름 금지어 관리",
        guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    def __init__(self, bot):
        self.bot = bot
        self.recent: dict[tuple[int, int], dict] = {}

    @group.command(name="추가", description="금지어를 추가합니다. (공백/특수문자/대소문자 무시)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add_word(self, interaction: discord.Interaction, 단어: app_commands.Range[str, 1, 30]):
        word = normalize(단어)
        if not word:
            return await reply(interaction, "❌ 추가 실패", "한글/영문/숫자가 포함된 단어를 입력해 주세요.", COLOR_ERR)
        ok = await self.bot.db.add_banned_word(interaction.guild.id, word)
        await reply(interaction, "✅ 금지어 추가" if ok else "ℹ️ 이미 있음",
                    f"`{esc(word)}` {'을(를) 추가했어요.' if ok else '은(는) 이미 등록되어 있어요.'}")

    @group.command(name="삭제", description="금지어를 삭제합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove_word(self, interaction: discord.Interaction, 단어: str):
        word = normalize(단어)
        ok = await self.bot.db.remove_banned_word(interaction.guild.id, word)
        await reply(interaction, "✅ 삭제 완료" if ok else "❌ 없음",
                    f"`{esc(word)}` {'을(를) 삭제했어요.' if ok else '은(는) 등록되어 있지 않아요.'}",
                    COLOR_WARN if not ok else discord.Colour.green())

    @remove_word.autocomplete("단어")
    async def remove_autocomplete(self, interaction: discord.Interaction, current: str):
        words = await self.bot.db.get_banned_words(interaction.guild.id)
        cur = normalize(current)
        return [app_commands.Choice(name=w, value=w) for w in words if cur in w][:25]

    @group.command(name="목록", description="등록된 금지어 목록을 봅니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list_words(self, interaction: discord.Interaction):
        words = await self.bot.db.get_banned_words(interaction.guild.id)
        lines = [f"`{i}.` {esc(w)}" for i, w in enumerate(words, 1)]
        view = PagedView(f"🚫 금지어 목록 · {len(words)}개", lines, per_page=20,
                         note="공백·특수문자·대소문자 무시", empty="등록된 금지어가 없어요.")
        await interaction.response.send_message(view=view, ephemeral=True)
        view.sent_message = await interaction.original_response()

    # ── 차단 로그 ──
    def build_card(self, member: discord.Member, lines: list[str], total: int) -> discord.ui.LayoutView:
        c = discord.ui.Container(accent_colour=COLOR_ERR if total >= 5 else COLOR_WARN)
        c.add_item(discord.ui.Section(
            discord.ui.TextDisplay("### 🚫 자기소개 차단 기록"),
            discord.ui.TextDisplay(f"{member.mention} · `{member.name}`"),
            discord.ui.TextDisplay(f"누적 시도: **{total}회**" + (" ⚠️" if total >= 5 else "")),
            accessory=discord.ui.Thumbnail(member.display_avatar.url)))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.TextDisplay("\n".join(lines)))
        c.add_item(discord.ui.TextDisplay(
            f"-# 최근 {FILTER_LOG_WINDOW // 60}분 내 시도는 이 카드에 묶여요 (최대 5개 표시)"))
        return as_view(c)

    async def log_attempt(self, guild: discord.Guild, member: discord.Member, raw: dict,
                          reason: str, category: str, matched: str | None):
        content = f"{raw.get('name') or '-'} / {raw.get('age') or '-'} / {raw.get('gender') or '-'} / {raw.get('route') or '-'}"[:200]
        label = CATEGORY_LABELS.get(category, category)
        await self.bot.db.add_filter_log(guild.id, member.id, content, f"{label}: {reason}")
        total = await self.bot.db.count_filter_logs(guild.id, member.id)

        s = await self.bot.db.get_settings(guild.id)
        ch = guild.get_channel(s["admin_channel_id"]) if s["admin_channel_id"] else None
        if ch is None:
            return
        tag = f"**{label}**" + (f" (`{esc(matched)}`)" if matched else "")
        line = f"<t:{now_ts()}:T> · {tag} · {esc(content)}"

        key, now = (guild.id, member.id), time.monotonic()
        entry = self.recent.get(key)
        if entry and now - entry["time"] < FILTER_LOG_WINDOW:
            entry["lines"] = (entry["lines"] + [line])[-5:]
            entry["time"] = now
            try:
                await entry["msg"].edit(view=self.build_card(member, entry["lines"], total))
                return
            except discord.HTTPException:
                pass
        try:
            msg = await ch.send(view=self.build_card(member, [line], total), allowed_mentions=NO_MENTIONS)
            self.recent[key] = {"msg": msg, "time": now, "lines": [line]}
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(Filter(bot))