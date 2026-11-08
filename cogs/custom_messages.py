import discord
from discord import app_commands
from discord.ext import commands

from config import COLOR_OK
from core.messages import MESSAGE_COLORS, MESSAGE_PLACEHOLDERS, MESSAGE_TYPES, fill, sample_vars
from core.ui import admin_command, as_view, make_container, reply

MSG_CHOICES = [app_commands.Choice(name=v, value=k) for k, v in MESSAGE_TYPES.items()]


def preview_view(guild, member, key, title, body, prefix, header=None) -> discord.ui.LayoutView:
    v = sample_vars(guild, member, prefix)
    items = []
    if header:
        items.append(make_container(*header, COLOR_OK))
    items.append(make_container(fill(title, v), fill(body, v), MESSAGE_COLORS[key]))
    return as_view(*items)


class MessageEditModal(discord.ui.Modal):
    def __init__(self, bot, key: str, title: str, body: str):
        super().__init__(title=f"문구 설정 · {MESSAGE_TYPES[key]}"[:45], timeout=1800)
        self.bot, self.key = bot, key
        self.title_input = discord.ui.TextInput(default=title, max_length=200)
        self.body_input = discord.ui.TextInput(style=discord.TextStyle.paragraph, default=body, max_length=3500)
        hints = " ".join(f"`{{{p}}}`" for p in MESSAGE_PLACEHOLDERS[key])
        self.add_item(discord.ui.TextDisplay(f"**사용 가능한 치환자**\n{hints}\n-# 마크다운(**굵게**, ### 제목, - 목록 등) 사용 가능"))
        self.add_item(discord.ui.Label(text="제목", component=self.title_input))
        self.add_item(discord.ui.Label(text="본문", component=self.body_input))

    async def on_submit(self, interaction: discord.Interaction):
        t, b = self.title_input.value, self.body_input.value
        await self.bot.db.set_message(interaction.guild.id, self.key, t, b)
        s = await self.bot.db.get_settings(interaction.guild.id)
        await interaction.response.send_message(
            view=preview_view(interaction.guild, interaction.user, self.key, t, b, s["nick_prefix"],
                              header=("✅ 저장 완료", f"**{MESSAGE_TYPES[self.key]}** 문구를 저장했어요. 아래는 예시 데이터로 만든 미리보기예요.")),
            ephemeral=True)


class CustomMessages(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="메시지설정", description="봇이 보내는 문구를 직접 수정합니다.")
    @app_commands.choices(종류=MSG_CHOICES)
    @admin_command()
    async def edit(self, interaction: discord.Interaction, 종류: str):
        title, body = await self.bot.db.get_message(interaction.guild.id, 종류)
        await interaction.response.send_modal(MessageEditModal(self.bot, 종류, title, body))

    @app_commands.command(name="메시지미리보기", description="현재 문구를 예시 데이터로 미리 봅니다.")
    @app_commands.choices(종류=MSG_CHOICES)
    @admin_command()
    async def preview(self, interaction: discord.Interaction, 종류: str):
        title, body = await self.bot.db.get_message(interaction.guild.id, 종류)
        s = await self.bot.db.get_settings(interaction.guild.id)
        await interaction.response.send_message(
            view=preview_view(interaction.guild, interaction.user, 종류, title, body, s["nick_prefix"]), ephemeral=True)

    @app_commands.command(name="메시지초기화", description="문구를 기본값으로 되돌립니다.")
    @app_commands.choices(종류=MSG_CHOICES)
    @admin_command()
    async def reset(self, interaction: discord.Interaction, 종류: str):
        await self.bot.db.reset_message(interaction.guild.id, 종류)
        await reply(interaction, "✅ 초기화 완료", f"**{MESSAGE_TYPES[종류]}** 문구를 기본값으로 되돌렸어요.")


async def setup(bot):
    await bot.add_cog(CustomMessages(bot))