print(">>> 실행 중 파일:", __file__)

import os
import json
import asyncio
import discord #
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

PREFIX_TAG = "대기_"
PANEL_TITLE = "대기 모드 패널"
CONFIG_FILE = "panel_config.json"
AUTO_DELETE_SECONDS = 5

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ===== 설정 저장/로드 =====
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

panel_channel_map = load_config()


# ===== 접두사 유틸 =====
def strip_all_prefixes(name: str) -> str:
    while name.startswith(PREFIX_TAG):
        name = name[len(PREFIX_TAG):]
    return name


# ===== 패널 채널 선택 =====
def pick_panel_channel(guild: discord.Guild):
    priority = ["대기-봇", "대기", "대기-패널"]
    me = guild.me

    channels = [
        c for c in guild.text_channels
        if c.permissions_for(me).send_messages
    ]
    if not channels:
        return None

    for wanted in priority:
        for ch in channels:
            if wanted in ch.name.lower():
                return ch

    return sorted(channels, key=lambda c: c.position)[0]


# ===== 패널 자동 설치 =====
async def ensure_panel_once(guild: discord.Guild):
    gid = str(guild.id)
    channel = None

    if gid in panel_channel_map:
        cid = panel_channel_map[gid]
        ch = guild.get_channel(cid)
        if ch and ch.permissions_for(guild.me).send_messages:
            channel = ch

    if channel is None:
        channel = pick_panel_channel(guild)

    if channel is None:
        print(f"⚠️ {guild.name}: 패널 설치할 채널 없음")
        return

    try:
        async for msg in channel.history(limit=20):
            if msg.author == guild.me and msg.embeds:
                if msg.embeds[0].title == PANEL_TITLE:
                    print(f"✅ 기존 패널 유지: {channel.name}")
                    return
    except:
        pass

    embed = discord.Embed(
        title=PANEL_TITLE,
        description="버튼으로 닉네임 앞에 `대기_`을 붙이거나 뗄 수 있어요.\n본인 닉네임만 변경됩니다."
    )
    await channel.send(embed=embed, view=waitView())
    print(f"✅ 패널 자동 설치 완료: {channel.name}")


# ===== 버튼 =====
class waitView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # ===== 활성화 =====
    @discord.ui.button(label="활성화", style=discord.ButtonStyle.success, custom_id="wait_on")
    async def activate(self, interaction: discord.Interaction, _):
        member = interaction.user
        me = interaction.guild.me

        # 권한/역할 체크
        if member.guild.owner_id == member.id:
            await self.ephemeral_delete(interaction, "서버 소유자는 자동 닉변 불가.")
            return
        if not interaction.app_permissions.manage_nicknames:
            await self.ephemeral_delete(interaction, "봇에 닉네임 변경 권한 없음.")
            return
        if me.top_role <= member.top_role:
            await self.ephemeral_delete(interaction, "봇 역할이 멤버보다 아래임.")
            return

        base = member.nick if member.nick else member.name
        clean = strip_all_prefixes(base)
        new_nick = PREFIX_TAG + clean

        if member.nick == new_nick:
            await self.ephemeral_delete(interaction, "이미 활성화 상태 ✅")
            await interaction.channel.send(
                f"{member.mention} 이미 `대기_` 접두사가 적용됨.",
                delete_after=AUTO_DELETE_SECONDS
            )
            return

        await member.edit(nick=new_nick, reason="대기 활성화")

        await self.ephemeral_delete(interaction, "✅ 대기 모드 활성화!")
        


    # ===== 비활성화 =====
    @discord.ui.button(label="비활성화", style=discord.ButtonStyle.danger, custom_id="wait_off")
    async def deactivate(self, interaction: discord.Interaction, _):
        member = interaction.user
        me = interaction.guild.me

        if member.guild.owner_id == member.id:
            await self.ephemeral_delete(interaction, "서버 소유자는 자동 해제 불가.")
            return
        if not interaction.app_permissions.manage_nicknames:
            await self.ephemeral_delete(interaction, "봇에 닉변 권한 없음.")
            return
        if me.top_role <= member.top_role:
            await self.ephemeral_delete(interaction, "봇 역할이 멤버보다 아래임.")
            return

        current = member.nick if member.nick else member.name
        clean = strip_all_prefixes(current)

        if current == clean:
            await self.ephemeral_delete(interaction, "이미 비활성화 상태 ✅")
            return

        await member.edit(nick=clean, reason="대기 비활성화")

        await self.ephemeral_delete(interaction, "✅ 대기 모드 해제됨.")
        


    # ===== 에페메랄(본인만 보이는 메시지도 자동 삭제) =====
    async def ephemeral_delete(self, interaction: discord.Interaction, text: str):
        """에페메랄 메시지를 보내고 5초 뒤 자동 삭제."""
        await interaction.response.send_message(text, ephemeral=True)
        try:
            msg = await interaction.original_response()
            await asyncio.sleep(AUTO_DELETE_SECONDS)
            await msg.delete()
        except:
            pass



# ===== 이벤트 =====
@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")
    bot.add_view(waitView())

    try:
        synced = await bot.tree.sync()
        print(f"✅ Slash synced: {len(synced)}")
    except Exception as e:
        print(f"❌ Slash sync error: {e}")

    for guild in bot.guilds:
        await ensure_panel_once(guild)


@bot.event
async def on_guild_join(guild):
    try:
        await bot.tree.sync(guild=guild)
    except:
        pass
    await ensure_panel_once(guild)



# ===== 관리자 명령 =====
@bot.tree.command(name="대기채널설정", description="대기 패널을 띄울 채널을 지정합니다.")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_panel_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    panel_channel_map[str(interaction.guild_id)] = channel.id
    save_config(panel_channel_map)
    await interaction.response.send_message(
        f"✅ 이제 대기 패널은 {channel.mention} 에 표시됩니다.",
        ephemeral=True
    )
    await ensure_panel_once(interaction.guild)



# ===== 실행 =====
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN이 비어있어요 (.env 또는 Railway Variables 확인)")


bot.run(TOKEN)
