import discord
from discord import app_commands
from discord.ext import commands

from config import COLOR_ERR, COLOR_INFO, COLOR_OK, COLOR_WARN, MAIN_CHANNELS_MAX, NICK_PREFIX_MAX, NAME_MAX
from core.messages import SAMPLE_DATA, esc, fill, tvars
from core.ui import (NO_MENTIONS, ONOFF, admin_command, as_view, build_panel_view,
                     build_welcome_view, reply)
from core.validators import BRACKETS
from core.verification import build_nick, check_role, lock_intro_channel

AGE_CHOICES = [
    app_commands.Choice(name=f"{k} ({a}~{b}세)" if a != b else f"{k} ({a}세)", value=k)
    for k, a, b in BRACKETS
][:25]
AnyChannel = discord.TextChannel | discord.VoiceChannel | discord.ForumChannel


def can_send(channel: discord.abc.GuildChannel) -> bool:
    p = channel.permissions_for(channel.guild.me)
    return p.view_channel and p.send_messages


class Settings(commands.Cog):
    main_group = app_commands.Group(
        name="주요채널", description="환영 DM에 표시할 주요 채널 관리",
        guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    def __init__(self, bot):
        self.bot = bot

    async def _set_channel(self, interaction, channel, key, title, desc):
        if not can_send(channel):
            return await reply(interaction, "❌ 설정 실패", f"{channel.mention} 에 봇이 메시지를 보낼 권한이 없어요.", COLOR_ERR)
        await self.bot.db.set_settings(interaction.guild.id, **{key: channel.id})
        await reply(interaction, f"✅ {title}", f"{channel.mention} {desc}")

    # ── 채널 ──
    @app_commands.command(name="자기소개채널", description="자기소개 버튼을 올릴 채널을 설정합니다.")
    @admin_command()
    async def intro_channel(self, interaction: discord.Interaction, 채널: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.set_settings(interaction.guild.id, intro_channel_id=채널.id)
        lock = await lock_intro_channel(interaction.guild, await self.bot.db.get_settings(interaction.guild.id))
        await reply(interaction, "✅ 자기소개 채널 설정",
                    f"{채널.mention} 을(를) 자기소개 채널로 설정했어요.\n{lock}\n\n`/안내양식` 으로 버튼 메시지를 올려주세요.")

    @app_commands.command(name="안내로그", description="자기소개/재입장 복구 로그 채널을 설정합니다.")
    @admin_command()
    async def log_channel(self, interaction: discord.Interaction, 채널: discord.TextChannel):
        await self._set_channel(interaction, 채널, "log_channel_id", "안내로그 채널 설정", "으로 자기소개 로그가 전송돼요.")

    @app_commands.command(name="퇴장로그", description="퇴장 로그 채널을 설정합니다. (관리자 전용 채널 권장)")
    @admin_command()
    async def leave_channel(self, interaction: discord.Interaction, 채널: discord.TextChannel):
        await self._set_channel(interaction, 채널, "leave_channel_id", "퇴장로그 채널 설정", "으로 퇴장 로그가 전송돼요.")

    @app_commands.command(name="관리자채널", description="/안내기록 사용 + 차단 기록이 전송될 관리자 채널을 설정합니다.")
    @admin_command()
    async def admin_channel(self, interaction: discord.Interaction, 채널: discord.TextChannel):
        await self._set_channel(interaction, 채널, "admin_channel_id", "관리자 채널 설정",
                                "에서 `/안내기록` 을 사용할 수 있고, 차단 기록도 여기로 전송돼요.")

    # ── 역할 ──
    @app_commands.command(name="인증역할", description="인증 완료 시 지급할 역할을 설정합니다.")
    @admin_command()
    async def verified_role(self, interaction: discord.Interaction, 역할: discord.Role):
        if err := check_role(역할, interaction.guild):
            return await reply(interaction, "❌ 설정 실패", err, COLOR_ERR)
        await self.bot.db.set_settings(interaction.guild.id, role_id=역할.id)
        await reply(interaction, "✅ 인증 역할 설정", f"인증 완료 시 {역할.mention} 이(가) 지급돼요.")

    @app_commands.command(name="미인증역할", description="입장 시 자동 지급되고 인증 시 제거될 역할을 설정합니다.")
    @admin_command()
    async def unverified_role(self, interaction: discord.Interaction, 역할: discord.Role):
        if err := check_role(역할, interaction.guild):
            return await reply(interaction, "❌ 설정 실패", err, COLOR_ERR)
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.set_settings(interaction.guild.id, unverified_role_id=역할.id)
        lock = await lock_intro_channel(interaction.guild, await self.bot.db.get_settings(interaction.guild.id))
        await reply(interaction, "✅ 미인증 역할 설정",
                    f"입장 시 {역할.mention} 자동 지급, 인증 시 제거돼요.\n{lock}\n\n"
                    f"-# 💡 `/미인증잠금적용` 으로 자기소개 채널만 보이게 설정하세요.")

    @app_commands.command(name="성별역할", description="성별에 따라 지급할 역할을 설정합니다.")
    @admin_command()
    async def gender_role(self, interaction: discord.Interaction, 남자역할: discord.Role, 여자역할: discord.Role):
        for r in (남자역할, 여자역할):
            if err := check_role(r, interaction.guild):
                return await reply(interaction, "❌ 설정 실패", err, COLOR_ERR)
        await self.bot.db.set_settings(interaction.guild.id, male_role_id=남자역할.id, female_role_id=여자역할.id)
        await reply(interaction, "✅ 성별 역할 설정", f"남자: {남자역할.mention}\n여자: {여자역할.mention}")

    @app_commands.command(name="나이역할", description="나이대 구간별 역할을 설정합니다. (역할 비우면 해제)")
    @app_commands.choices(구간=AGE_CHOICES)
    @admin_command()
    async def age_role(self, interaction: discord.Interaction, 구간: str, 역할: discord.Role | None = None):
        if 역할 and (err := check_role(역할, interaction.guild)):
            return await reply(interaction, "❌ 설정 실패", err, COLOR_ERR)
        await self.bot.db.set_age_role(interaction.guild.id, 구간, 역할.id if 역할 else None)
        await reply(interaction, "✅ 나이 역할 설정", f"**{구간}** → {역할.mention if 역할 else '해제됨'}")

    @app_commands.command(name="역할자동생성", description="미인증, 남자/여자, 모든 나이대 역할을 자동으로 만들고 등록합니다.")
    @admin_command()
    async def auto_roles(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild, gid = interaction.guild, interaction.guild.id
        s = await self.bot.db.get_settings(gid)
        created, reused, failed = [], [], []

        async def get_or_create(name: str) -> discord.Role | None:
            role = discord.utils.get(guild.roles, name=name)
            if role:
                if role >= guild.me.top_role:
                    failed.append(f"{name} (봇보다 높음)")
                    return None
                reused.append(name)
                return role
            try:
                role = await guild.create_role(name=name, reason="안내봇 역할 자동 생성")
                created.append(name)
                return role
            except discord.HTTPException:
                failed.append(name)
                return None

        if not s["unverified_role_id"] and (r := await get_or_create("미인증")):
            await self.bot.db.set_settings(gid, unverified_role_id=r.id)
        for gender, key in (("남자", "male_role_id"), ("여자", "female_role_id")):
            if r := await get_or_create(gender):
                await self.bot.db.set_settings(gid, **{key: r.id})
        for bracket, _, _ in BRACKETS:
            if r := await get_or_create(bracket):
                await self.bot.db.set_age_role(gid, bracket, r.id)

        body = (f"🆕 새로 생성 ({len(created)}): {', '.join(created) or '없음'}\n"
                f"♻️ 기존 역할 사용 ({len(reused)}): {', '.join(reused) or '없음'}")
        if failed:
            body += f"\n❌ 실패 ({len(failed)}): {', '.join(failed)}"
        await reply(interaction, "✅ 역할 자동 생성 완료", body, COLOR_WARN if failed else COLOR_OK)

    # ── 미인증 잠금 ──
    @app_commands.command(name="미인증잠금적용", description="미인증 역할이 자기소개 채널 외 모든 채널을 못 보게 설정합니다.")
    @admin_command()
    async def apply_lock(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        s = await self.bot.db.get_settings(guild.id)
        role = guild.get_role(s["unverified_role_id"]) if s["unverified_role_id"] else None
        intro = guild.get_channel(s["intro_channel_id"]) if s["intro_channel_id"] else None
        if not role or not intro:
            return await reply(interaction, "❌ 적용 실패", "`/미인증역할` 과 `/자기소개채널` 을 먼저 설정해 주세요.", COLOR_ERR)

        done, skipped, failed = 0, 0, []
        for ch in guild.channels:
            if ch.id == intro.id:
                continue
            ow = ch.overwrites_for(role)
            if ow.view_channel is False:
                skipped += 1
                continue
            ow.view_channel = False
            try:
                await ch.set_permissions(role, overwrite=ow, reason="미인증 잠금 적용")
                done += 1
            except discord.HTTPException:
                failed.append(ch.name)
        lock = await lock_intro_channel(guild, s)
        body = f"🔒 적용 {done}개 · 이미 적용됨 {skipped}개\n{lock}"
        if failed:
            body += f"\n❌ 실패 ({len(failed)}): {', '.join(esc(n) for n in failed[:15])}"
        body += "\n\n-# 기존 멤버는 미인증 역할이 없으므로 영향이 없어요."
        await reply(interaction, "✅ 미인증 잠금 적용", body, COLOR_WARN if failed else COLOR_OK)

    @app_commands.command(name="미인증잠금자동", description="새로 만든 채널에 미인증 잠금을 자동 적용할지 설정합니다.")
    @app_commands.choices(상태=ONOFF)
    @admin_command()
    async def auto_lock(self, interaction: discord.Interaction, 상태: str):
        await self.bot.db.set_settings(interaction.guild.id, unv_lock_auto=1 if 상태 == "on" else 0)
        await reply(interaction, "✅ 미인증 잠금 자동 적용", f"상태: **{'켜짐' if 상태 == 'on' else '꺼짐'}**")

    # ── 닉네임 / 기능 ──
    @app_commands.command(name="인증닉네임설정", description="인증 시 이름 앞에 붙을 접두사를 설정합니다. (비우면 초기화)")
    @app_commands.describe(닉네임="예: 「뉴 페이스 ⌢♡」")
    @admin_command()
    async def nick_prefix(self, interaction: discord.Interaction, 닉네임: str | None = None):
        prefix = 닉네임 or ""
        if len(prefix) > NICK_PREFIX_MAX:
            return await reply(interaction, "❌ 설정 실패",
                               f"접두사는 최대 **{NICK_PREFIX_MAX}자**까지 가능해요.\n-# 닉네임 32자 − 이름 최대 {NAME_MAX}자", COLOR_ERR)
        await self.bot.db.set_settings(interaction.guild.id, nick_prefix=prefix)
        await reply(interaction, "✅ 인증 닉네임 설정",
                    f"접두사: {esc(prefix) or '(없음)'}\n미리보기: **{esc(build_nick(prefix, '홍길동'))}**\n\n"
                    f"-# 이미 인증한 유저는 인증 당시 접두사를 유지해요.")

    @app_commands.command(name="부계정경고", description="계정 생성일이 짧은 유저를 로그에 빨간색으로 표시합니다.")
    @app_commands.choices(상태=ONOFF)
    @admin_command()
    async def alt_warn(self, interaction: discord.Interaction, 상태: str,
                       기준일수: app_commands.Range[int, 1, 365] | None = None):
        values = {"alt_warn_enabled": 1 if 상태 == "on" else 0}
        if 기준일수:
            values["alt_warn_days"] = 기준일수
        await self.bot.db.set_settings(interaction.guild.id, **values)
        s = await self.bot.db.get_settings(interaction.guild.id)
        await reply(interaction, "✅ 부계정 경고 설정",
                    f"상태: **{'켜짐' if s['alt_warn_enabled'] else '꺼짐'}** · 기준: 계정 생성 **{s['alt_warn_days']}일 미만**")

    @app_commands.command(name="환영dm", description="인증 완료 시 환영 DM을 켜거나 끄거나 미리봅니다.")
    @app_commands.choices(상태=ONOFF + [app_commands.Choice(name="미리보기", value="preview")])
    @admin_command()
    async def welcome_dm(self, interaction: discord.Interaction, 상태: str):
        if 상태 == "preview":
            view = await build_welcome_view(self.bot, interaction.guild, interaction.user, SAMPLE_DATA)
            return await interaction.response.send_message(view=view, ephemeral=True)
        await self.bot.db.set_settings(interaction.guild.id, welcome_dm_enabled=1 if 상태 == "on" else 0)
        await reply(interaction, "✅ 환영 DM 설정",
                    f"상태: **{'켜짐' if 상태 == 'on' else '꺼짐'}**\n-# 문구는 `/메시지설정`, 채널은 `/주요채널` 로 설정해요.")

    @main_group.command(name="추가", description="환영 DM에 주요 채널을 추가합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def main_add(self, interaction: discord.Interaction, 채널: AnyChannel, 설명: app_commands.Range[str, 1, 100]):
        current = await self.bot.db.get_main_channels(interaction.guild.id)
        if len(current) >= MAIN_CHANNELS_MAX and 채널.id not in [c for c, _ in current]:
            return await reply(interaction, "❌ 추가 실패", f"주요 채널은 최대 **{MAIN_CHANNELS_MAX}개**까지 가능해요.", COLOR_ERR)
        await self.bot.db.add_main_channel(interaction.guild.id, 채널.id, 설명)
        await reply(interaction, "✅ 주요 채널 추가", f"{채널.mention}: {esc(설명)}")

    @main_group.command(name="삭제", description="환영 DM에서 주요 채널을 삭제합니다.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def main_remove(self, interaction: discord.Interaction, 채널: AnyChannel):
        ok = await self.bot.db.remove_main_channel(interaction.guild.id, 채널.id)
        await reply(interaction, "✅ 삭제 완료" if ok else "❌ 없음",
                    f"{채널.mention} {'을(를) 삭제했어요.' if ok else '은(는) 등록되어 있지 않아요.'}",
                    COLOR_OK if ok else COLOR_ERR)

    # ── 안내 패널 ──
    @app_commands.command(name="안내양식", description="자기소개 채널에 [📝 자기소개 작성] 버튼 메시지를 올립니다.")
    @admin_command()
    async def post_panel(self, interaction: discord.Interaction):
        guild = interaction.guild
        s = await self.bot.db.get_settings(guild.id)
        ch = guild.get_channel(s["intro_channel_id"]) if s["intro_channel_id"] else None
        if ch is None:
            return await reply(interaction, "❌ 실패", "먼저 `/자기소개채널` 을 설정해 주세요.", COLOR_ERR)
        if not can_send(ch):
            return await reply(interaction, "❌ 실패", f"{ch.mention} 에 메시지를 보낼 권한이 없어요.", COLOR_ERR)
        title, body = await self.bot.db.get_message(guild.id, "guide")
        v = tvars(guild)
        await ch.send(view=build_panel_view(guild, fill(title, v), fill(body, v)), allowed_mentions=NO_MENTIONS)
        await reply(interaction, "✅ 전송 완료", f"{ch.mention} 에 자기소개 버튼 메시지를 올렸어요.")

    # ── 설정 확인 ──
    @app_commands.command(name="설정확인", description="현재 안내봇 설정을 확인합니다.")
    @admin_command()
    async def show(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        db = self.bot.db
        s = await db.get_settings(gid)
        age_roles = await db.get_age_roles(gid)
        mains = await db.get_main_channels(gid)
        exempt = await db.get_exempt_roles(gid)
        banned = await db.get_banned_words(gid)

        def ch(i): return f"<#{i}>" if i else "미설정"
        def rl(i): return f"<@&{i}>" if i else "미설정"
        def on(x): return "켜짐" if x else "꺼짐"

        blocks = [
            "**📡 채널**\n"
            f"📝 자기소개: {ch(s['intro_channel_id'])} · 📨 안내로그: {ch(s['log_channel_id'])}\n"
            f"📤 퇴장로그: {ch(s['leave_channel_id'])} · 🛡️ 관리자: {ch(s['admin_channel_id'])}",
            "**🎖️ 역할**\n"
            f"인증: {rl(s['role_id'])} · 미인증: {rl(s['unverified_role_id'])}\n"
            f"남자: {rl(s['male_role_id'])} · 여자: {rl(s['female_role_id'])}\n"
            f"나이대 ({len(age_roles)}/{len(BRACKETS)}): "
            + (", ".join(f"<@&{age_roles[b]}>" for b, _, _ in BRACKETS if b in age_roles) or "미설정"),
            "**⏰ 미인증 처리**\n"
            f"상태: {on(s['unv_enabled'])}" + (f" (<t:{s['unv_since']}:D> 이후 입장자)" if s["unv_enabled"] and s["unv_since"] else "")
            + f"\n알림 {s['unv_warn_hours']}시간 → 추방 {s['unv_kick_hours']}시간 · 예외 역할 {len(exempt)}개\n"
            f"새 채널 자동 잠금: {on(s['unv_lock_auto'])}",
            "**🏷️ 기타**\n"
            f"닉네임 접두사: {esc(s['nick_prefix']) or '(없음)'}\n"
            f"뉴 페이스 자동 제거: {on(s['newface_enabled'])} ({s['newface_days']}일)\n"
            f"부계정 경고: {on(s['alt_warn_enabled'])} ({s['alt_warn_days']}일 미만)\n"
            f"환영 DM: {on(s['welcome_dm_enabled'])} · 주요 채널 {len(mains)}개 · 금지어 {len(banned)}개",
        ]
        c = discord.ui.Container(accent_colour=COLOR_INFO)
        c.add_item(discord.ui.TextDisplay("### ⚙️ 현재 설정"))
        for b in blocks:
            c.add_item(discord.ui.Separator())
            c.add_item(discord.ui.TextDisplay(b))
        await interaction.response.send_message(view=as_view(c), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Settings(bot))