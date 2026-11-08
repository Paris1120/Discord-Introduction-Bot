import logging

import discord
from discord.ext import commands

from config import AGE_MAX, AGE_MIN, COLOR_ERR, GENDERS, NAME_MAX, NAME_MIN, ROUTES
from core.messages import esc, tvars
from core.ui import (as_view, build_welcome_view, custom_container, intro_log_card,
                     persistent_panel_view, reply, send_to)
from core.validators import validate_intro
from core.verification import apply_verification, build_nick, is_verified

log = logging.getLogger("guide-bot.intro")


class IntroModal(discord.ui.Modal):
    def __init__(self, cog: "Intro", prefill: dict | None = None):
        super().__init__(title="📝 자기소개 작성", timeout=900)
        self.cog = cog
        p = prefill or {}
        self.name_input = discord.ui.TextInput(
            placeholder="예: 홍길동", min_length=NAME_MIN, max_length=NAME_MAX, default=p.get("name") or None)
        self.age_input = discord.ui.TextInput(
            placeholder="예: 20", min_length=1, max_length=4, default=p.get("age") or None)
        self.gender_select = discord.ui.Select(
            placeholder="성별을 선택해 주세요",
            options=[discord.SelectOption(label=g, value=g, default=p.get("gender") == g) for g in GENDERS])
        self.route_select = discord.ui.Select(
            placeholder="서버를 알게 된 경로를 선택해 주세요",
            options=[discord.SelectOption(label=r, value=r, default=p.get("route") == r) for r in ROUTES])

        self.add_item(discord.ui.Label(
            text="이름", description=f"{NAME_MIN} ~ {NAME_MAX}자 · 특수문자 가능 · 영문, 숫자 불가", component=self.name_input))
        self.add_item(discord.ui.Label(
            text="나이", description=f"{AGE_MIN} ~ {AGE_MAX} 사이의 숫자", component=self.age_input))
        self.add_item(discord.ui.Label(text="성별", component=self.gender_select))
        self.add_item(discord.ui.Label(text="경로", component=self.route_select))

    async def on_submit(self, interaction: discord.Interaction):
        raw = {
            "name": self.name_input.value.strip(),
            "age": self.age_input.value.strip(),
            "gender": self.gender_select.values[0] if self.gender_select.values else "",
            "route": self.route_select.values[0] if self.route_select.values else "",
        }
        await self.cog.handle_submit(interaction, raw)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("자기소개 모달 오류", exc_info=error)
        await reply(interaction, "❌ 오류", "처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", COLOR_ERR)


class RetryView(discord.ui.LayoutView):
    def __init__(self, cog: "Intro", container: discord.ui.Container, raw: dict):
        super().__init__(timeout=900)
        self.cog, self.raw = cog, raw
        btn = discord.ui.Button(label="다시 작성", emoji="✏️", style=discord.ButtonStyle.primary)
        btn.callback = self.retry
        row = discord.ui.ActionRow()
        row.add_item(btn)
        container.add_item(row)
        self.add_item(container)

    async def retry(self, interaction: discord.Interaction):
        await self.cog.open_modal(interaction, self.raw)


class ConfirmView(discord.ui.LayoutView):
    def __init__(self, cog: "Intro", container: discord.ui.Container, data: dict, raw: dict):
        super().__init__(timeout=900)
        self.cog, self.data, self.raw = cog, data, raw
        submit = discord.ui.Button(label="제출", emoji="✅", style=discord.ButtonStyle.success)
        edit = discord.ui.Button(label="수정", emoji="✏️", style=discord.ButtonStyle.secondary)
        submit.callback = self.submit
        edit.callback = self.edit
        row = discord.ui.ActionRow()
        row.add_item(submit)
        row.add_item(edit)
        container.add_item(row)
        self.add_item(container)

    async def submit(self, interaction: discord.Interaction):
        self.stop()
        await self.cog.finalize(interaction, self.data)

    async def edit(self, interaction: discord.Interaction):
        await self.cog.open_modal(interaction, self.raw)


class Intro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(persistent_panel_view())

    async def notice(self, interaction: discord.Interaction, key: str, **extra):
        v = tvars(interaction.guild, interaction.user, **extra)
        view = as_view(await custom_container(self.bot, interaction.guild, key, v))
        if interaction.response.is_done():
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    async def open_modal(self, interaction: discord.Interaction, prefill: dict | None = None):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return
        s = await self.bot.db.get_settings(interaction.guild.id)
        if not s["intro_channel_id"]:
            return await reply(interaction, "❌ 사용 불가", "자기소개 기능이 아직 설정되지 않았어요.", COLOR_ERR)
        key = (interaction.guild.id, interaction.user.id)
        if key in self.bot.processing or await is_verified(self.bot, interaction.user, s):
            return await self.notice(interaction, "already_verified")
        await interaction.response.send_modal(IntroModal(self, prefill))

    async def handle_submit(self, interaction: discord.Interaction, raw: dict):
        guild, member = interaction.guild, interaction.user
        s = await self.bot.db.get_settings(guild.id)
        if await is_verified(self.bot, member, s):
            return await self.notice(interaction, "already_verified")

        banned = await self.bot.db.get_banned_words(guild.id)
        data, err, category, matched = validate_intro(raw, banned)
        if err:
            container = await custom_container(self.bot, guild, "form_error", tvars(guild, member, 이유=err))
            await interaction.response.send_message(view=RetryView(self, container, raw), ephemeral=True)
            filt = self.bot.get_cog("Filter")
            if filt:
                await filt.log_attempt(guild, member, raw, err, category, matched)
            return

        nick = build_nick(s["nick_prefix"], data["name"])
        container = await custom_container(self.bot, guild, "confirm", tvars(guild, member, data, 닉네임=esc(nick)))
        await interaction.response.send_message(view=ConfirmView(self, container, data, raw), ephemeral=True)

    async def finalize(self, interaction: discord.Interaction, data: dict):
        await interaction.response.defer()
        guild, member = interaction.guild, interaction.user
        key = (guild.id, member.id)
        s = await self.bot.db.get_settings(guild.id)

        if key in self.bot.processing or await is_verified(self.bot, member, s):
            v = tvars(guild, member)
            return await interaction.edit_original_response(
                view=as_view(await custom_container(self.bot, guild, "already_verified", v)))

        self.bot.processing.add(key)
        try:
            prefix = s["nick_prefix"]
            await self.bot.db.add_intro(guild.id, member.id, data, prefix)
            await self.bot.db.delete_unv_warn(guild.id, member.id)
            warnings, new_nick = await apply_verification(self.bot, member, data, s, prefix)

            if s["welcome_dm_enabled"]:
                try:
                    await member.send(view=await build_welcome_view(self.bot, guild, member, data))
                except discord.HTTPException:
                    warnings.append("환영 DM 전송 실패 (유저가 DM 차단)")

            await send_to(guild, s["log_channel_id"], intro_log_card(member, data, warnings, new_nick, s))
            v = tvars(guild, member, data, 닉네임=esc(new_nick or data["name"]))
            await interaction.edit_original_response(
                view=as_view(await custom_container(self.bot, guild, "complete", v)))
        except Exception:
            log.exception("인증 처리 오류")
            await interaction.edit_original_response(view=as_view(
                await custom_container(self.bot, guild, "form_error",
                                       tvars(guild, member, 이유="처리 중 오류가 발생했어요. 관리자에게 문의해 주세요."))))
        finally:
            self.bot.processing.discard(key)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """자기소개 채널에 올라온 채팅은 자동 삭제 (관리자 제외)"""
        if message.author.bot or message.guild is None or not isinstance(message.author, discord.Member):
            return
        s = await self.bot.db.get_settings(message.guild.id)
        if message.channel.id != s["intro_channel_id"] or message.author.guild_permissions.manage_guild:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(Intro(bot))