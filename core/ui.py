import logging
from datetime import datetime, timezone

import discord
from discord import app_commands

from config import COLOR_ERR, COLOR_INFO, COLOR_OK, COLOR_WARN, MAIN_CHANNELS_MAX, RECORDS_PER_PAGE
from core.messages import MESSAGE_COLORS, esc, fill, now_ts, tvars
from core.validators import age_bracket

log = logging.getLogger("guide-bot.ui")

INTRO_BUTTON_ID = "guide:intro:start"
ONOFF = [app_commands.Choice(name="켜기", value="on"), app_commands.Choice(name="끄기", value="off")]
NO_MENTIONS = discord.AllowedMentions.none()


def admin_command():
    """서버 관리 권한 전용 + 서버에서만 사용 (@app_commands.command 아래에 붙이기)"""
    def deco(func):
        func = app_commands.checks.has_permissions(manage_guild=True)(func)
        func = app_commands.default_permissions(manage_guild=True)(func)
        return app_commands.guild_only()(func)
    return deco


# ── 기본 빌더 ──
def make_container(title: str, body: str, colour: discord.Colour, footer: str | None = None) -> discord.ui.Container:
    c = discord.ui.Container(accent_colour=colour)
    c.add_item(discord.ui.TextDisplay(f"### {title}"))
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(body))
    if footer:
        c.add_item(discord.ui.TextDisplay(f"-# {footer}"))
    return c


def as_view(*items, timeout: float | None = None) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=timeout)
    for item in items:
        view.add_item(item)
    return view


async def reply(interaction: discord.Interaction, title: str, body: str,
                colour: discord.Colour = COLOR_OK, ephemeral: bool = True):
    view = as_view(make_container(title, body, colour))
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(view=view, ephemeral=ephemeral)


async def custom_container(bot, guild: discord.Guild, key: str, v: dict,
                           footer: str | None = None) -> discord.ui.Container:
    title, body = await bot.db.get_message(guild.id, key)
    return make_container(fill(title, v), fill(body, v), MESSAGE_COLORS[key], footer=footer)


async def send_to(guild: discord.Guild, channel_id: int | None, view: discord.ui.LayoutView) -> discord.Message | None:
    ch = guild.get_channel(channel_id) if channel_id else None
    if ch is None:
        return None
    try:
        return await ch.send(view=view, allowed_mentions=NO_MENTIONS)
    except discord.HTTPException as e:
        log.warning(f"[{guild.name}] #{ch} 전송 실패: {e}")
        return None


def dm_card(title: str, body: str, colour: discord.Colour, guild: discord.Guild,
            link_label: str | None = None, link_url: str | None = None) -> discord.ui.LayoutView:
    c = discord.ui.Container(accent_colour=colour)
    head = discord.ui.TextDisplay(f"## {title}")
    if guild.icon:
        c.add_item(discord.ui.Section(head, accessory=discord.ui.Thumbnail(guild.icon.url)))
    else:
        c.add_item(head)
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(body))
    if link_url:
        row = discord.ui.ActionRow()
        row.add_item(discord.ui.Button(label=link_label or "바로가기", url=link_url))
        c.add_item(row)
    c.add_item(discord.ui.TextDisplay(f"-# {esc(guild.name)}에서 보낸 메시지입니다."))
    return as_view(c)


# ── 자기소개 패널 (영구 버튼) ──
class IntroStartButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="자기소개 작성", emoji="📝", style=discord.ButtonStyle.primary,
                         custom_id=INTRO_BUTTON_ID)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Intro")
        if cog:
            await cog.open_modal(interaction)


def build_panel_view(guild: discord.Guild, title: str, body: str) -> discord.ui.LayoutView:
    c = discord.ui.Container(accent_colour=MESSAGE_COLORS["guide"])
    head = discord.ui.TextDisplay(f"## {title}")
    if guild.icon:
        c.add_item(discord.ui.Section(head, accessory=discord.ui.Thumbnail(guild.icon.url)))
    else:
        c.add_item(head)
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(body))
    row = discord.ui.ActionRow()
    row.add_item(IntroStartButton())
    c.add_item(row)
    return as_view(c)


def persistent_panel_view() -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    row = discord.ui.ActionRow()
    row.add_item(IntroStartButton())
    view.add_item(row)
    return view


# ── 환영 DM ──
async def build_welcome_view(bot, guild: discord.Guild, member: discord.abc.User, data: dict) -> discord.ui.LayoutView:
    title, body = await bot.db.get_message(guild.id, "welcome_dm")
    v = tvars(guild, member, data)
    c = discord.ui.Container(accent_colour=MESSAGE_COLORS["welcome_dm"])
    head = discord.ui.TextDisplay(f"## {fill(title, v)}")
    if guild.icon:
        c.add_item(discord.ui.Section(head, accessory=discord.ui.Thumbnail(guild.icon.url)))
    else:
        c.add_item(head)
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(fill(body, v)))

    chans = [(guild.get_channel(cid), desc) for cid, desc in await bot.db.get_main_channels(guild.id)]
    chans = [(ch, d) for ch, d in chans if ch][:MAIN_CHANNELS_MAX]
    if chans:
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.TextDisplay("### 📌 주요 채널"))
        for ch, desc in chans:
            c.add_item(discord.ui.Section(
                discord.ui.TextDisplay(f"**#{esc(ch.name)}**\n{esc(desc)}"),
                accessory=discord.ui.Button(label="바로가기", url=ch.jump_url)))
    c.add_item(discord.ui.TextDisplay(f"-# {esc(guild.name)}에서 보낸 메시지입니다."))
    return as_view(c)


# ── 로그 카드 ──
def _profile_section(header: str, member: discord.Member, data: dict) -> discord.ui.Section:
    return discord.ui.Section(
        discord.ui.TextDisplay(header),
        discord.ui.TextDisplay(f"## {esc(data['name'])} / {data['age']} / {data['gender']} / {data['route']}"),
        discord.ui.TextDisplay(f"{member.mention} · `{member.name}`"),
        accessory=discord.ui.Thumbnail(member.display_avatar.url))


def _role_list(roles: list[discord.Role], limit: int = 20) -> str:
    if not roles:
        return "없음"
    text = ", ".join(r.mention for r in roles[:limit])
    return text + (f" 외 {len(roles) - limit}개" if len(roles) > limit else "")


def intro_log_card(member: discord.Member, data: dict, warnings: list[str], new_nick: str | None,
                   s: dict, edited_by: discord.abc.User | None = None) -> discord.ui.LayoutView:
    created = int(member.created_at.timestamp())
    days = (datetime.now(timezone.utc) - member.created_at).days
    alt = bool(s["alt_warn_enabled"]) and days < s["alt_warn_days"]
    colour = COLOR_ERR if alt else (COLOR_WARN if warnings else COLOR_OK)

    c = discord.ui.Container(accent_colour=colour)
    c.add_item(_profile_section("### ✏️ 자기소개 수정 (관리자)" if edited_by else "### 📥 새 자기소개", member, data))
    c.add_item(discord.ui.Separator())
    info = [f"🎂 나이대: **{age_bracket(data['age'])}**",
            f"🗓️ 계정 생성: <t:{created}:D> (<t:{created}:R>)"]
    if member.joined_at:
        info.append(f"📌 서버 입장: <t:{int(member.joined_at.timestamp())}:R>")
    if new_nick:
        info.append(f"🏷️ 닉네임: {esc(new_nick)}")
    if edited_by:
        info.append(f"🛠️ 수정자: {edited_by.mention}")
    c.add_item(discord.ui.TextDisplay("\n".join(info)))
    if alt:
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.TextDisplay(
            f"🚨 **부계정 의심** · 계정 생성 {days}일째 (기준: {s['alt_warn_days']}일 미만)"))
    if warnings:
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.TextDisplay("⚠️ **처리 경고**\n" + "\n".join(f"- {w}" for w in warnings)))
    c.add_item(discord.ui.TextDisplay(f"-# <t:{now_ts()}:F>"))
    return as_view(c)


def restore_log_card(member: discord.Member, data: dict, result: dict) -> discord.ui.LayoutView:
    warnings = list(result["warnings"])
    colour = COLOR_WARN if (warnings or result["high"]) else COLOR_INFO
    c = discord.ui.Container(accent_colour=colour)
    c.add_item(_profile_section("### 🔄 재입장 · 자동 복구", member, data))
    c.add_item(discord.ui.Separator())
    lines = [f"🎖️ 복구된 역할 ({len(result['restored'])}): {_role_list(result['restored'])}"]
    if result["danger"]:
        lines.append(f"🛡️ 관리 권한이라 제외: {_role_list(result['danger'])}")
    if result["high"]:
        lines.append(f"⛔ 봇보다 높아서 제외: {_role_list(result['high'])}")
    if result["missing"]:
        lines.append(f"🗑️ 삭제된 역할 {result['missing']}개 건너뜀")
    if result["nick"]:
        lines.append(f"🏷️ 닉네임: {esc(result['nick'])}")
    c.add_item(discord.ui.TextDisplay("\n".join(lines)))
    if warnings:
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.TextDisplay("⚠️ **처리 경고**\n" + "\n".join(f"- {w}" for w in warnings)))
    c.add_item(discord.ui.TextDisplay(f"-# <t:{now_ts()}:F>"))
    return as_view(c)


# ── 페이지 넘김 목록 ──
class PagedView(discord.ui.LayoutView):
    def __init__(self, heading: str, lines: list[str], colour: discord.Colour = COLOR_INFO,
                 per_page: int = RECORDS_PER_PAGE, subtitle: str | None = None,
                 note: str = "", empty: str = "항목이 없어요."):
        super().__init__(timeout=600)
        self.heading, self.lines, self.colour, self.per_page = heading, lines, colour, per_page
        self.subtitle, self.note, self.empty = subtitle, note, empty
        self.page = 0
        self.max_page = max(0, (len(lines) - 1) // per_page)
        self.expired = False
        self.sent_message: discord.Message | None = None
        self.render()

    def render(self):
        self.clear_items()
        c = discord.ui.Container(accent_colour=self.colour)
        c.add_item(discord.ui.TextDisplay(f"### {self.heading}"))
        if self.subtitle:
            c.add_item(discord.ui.TextDisplay(f"-# {self.subtitle}"))
        c.add_item(discord.ui.Separator())
        start = self.page * self.per_page
        chunk = self.lines[start:start + self.per_page]
        c.add_item(discord.ui.TextDisplay("\n".join(chunk) if chunk else self.empty))
        c.add_item(discord.ui.Separator())
        foot = f"-# 페이지 {self.page + 1} / {self.max_page + 1}"
        if self.note:
            foot += f" · {self.note}"
        if self.expired:
            foot += " · ⏱️ 만료됨"
        c.add_item(discord.ui.TextDisplay(foot))
        if self.max_page > 0:
            row = discord.ui.ActionRow()
            prev_btn = discord.ui.Button(label="◀ 이전", style=discord.ButtonStyle.secondary,
                                         disabled=self.expired or self.page == 0)
            next_btn = discord.ui.Button(label="다음 ▶", style=discord.ButtonStyle.secondary,
                                         disabled=self.expired or self.page >= self.max_page)
            prev_btn.callback = self._prev
            next_btn.callback = self._next
            row.add_item(prev_btn)
            row.add_item(next_btn)
            c.add_item(row)
        self.add_item(c)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                view=as_view(make_container("❌ 권한 없음", "관리자만 넘길 수 있어요.", COLOR_ERR)), ephemeral=True)
            return False
        return True

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self.render()
        await interaction.response.edit_message(view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page = min(self.max_page, self.page + 1)
        self.render()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        if self.max_page == 0 or not self.sent_message:
            return
        self.expired = True
        self.render()
        try:
            await self.sent_message.edit(view=self)
        except discord.HTTPException:
            pass