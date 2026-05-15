from __future__ import annotations

import aiohttp
import asyncio
import csv
import json
import logging
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import discord
from discord import app_commands
from dotenv import load_dotenv


# ============================================================
# NoxchoDictionary Premium Discord Bot
# Supports:
#   - Chechen Cyrillic
#   - Noxçiy Abat Latin
#   - Russian Cyrillic
#   - Russian Latin
#   - English
#
# Required API:
#   app.py running on http://127.0.0.1:27016
#
# Install:
#   pip install discord.py aiohttp python-dotenv
#
# Run:
#   python display_premium.py
# ============================================================


# ======= ENV / CONFIG =======

DEFAULT_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=os.getenv("ENV_PATH", str(DEFAULT_ENV_PATH)))

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
CHECHEN_API_URL = os.getenv("API_URL", "http://127.0.0.1:27016").rstrip("/")

# Optional: set this in .env for instant slash command sync while testing.
# TEST_GUILD_ID=123456789012345678
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")
TEST_GUILD_ID = int(TEST_GUILD_ID) if TEST_GUILD_ID and TEST_GUILD_ID.isdigit() else None

ADMIN_USER_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_USER_IDS", "1103698023768408165").split(",")
    if x.strip().isdigit()
}

DATA_DIR = Path(os.getenv("DATA_DIR", "bot_data"))
USER_STATS_FILE = DATA_DIR / "user_stats.json"
USER_MESSAGES_FILE = DATA_DIR / "user_messages.csv"
USER_SESSIONS_FILE = DATA_DIR / "user_sessions.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ======= LOGGING =======

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("NoxchoDictionary")


# ======= DISCORD CLIENT =======

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# ======= PREMIUM STYLE =======

BRAND_NAME = "NoxchoDictionary"
BRAND_ICON = "📚"
BRAND_FOOTER = "Noxçiy Abat • Chechen Dictionary"
API_TIMEOUT = aiohttp.ClientTimeout(total=20)

COLOR_PRIMARY = 0x2ECC71
COLOR_GOLD = 0xF4C542
COLOR_BLUE = 0x3498DB
COLOR_PURPLE = 0x9B59B6
COLOR_RED = 0xE74C3C
COLOR_DARK = 0x111827

ICON_CHECHEN = "🗣️"
ICON_LATIN = "🔤"
ICON_ENGLISH = "🇺🇸"
ICON_RUSSIAN = "🇷🇺"
ICON_CATEGORY = "🏷️"
ICON_TYPE = "🧩"
ICON_EXAMPLE = "💬"
ICON_SEARCH = "🔎"
ICON_RANDOM = "🎲"
ICON_STATS = "📊"
ICON_STAR = "✦"


SEARCH_MODE_CHOICES = [
    app_commands.Choice(name="Auto / All fields", value="all"),
    app_commands.Choice(name="Chechen Cyrillic", value="chechen"),
    app_commands.Choice(name="Chechen Latin - Noxçiy Abat", value="chechen_latin"),
    app_commands.Choice(name="Any Latin", value="latin"),
    app_commands.Choice(name="English", value="english"),
    app_commands.Choice(name="Russian Cyrillic", value="russian"),
    app_commands.Choice(name="Russian Latin", value="russian_latin"),
]


quiz_data: dict[int, dict[str, Any]] = {}
user_stats: dict[int, dict[str, Any]] = {}


# ============================================================
# DATA PERSISTENCE
# ============================================================

def load_user_stats() -> None:
    global user_stats
    try:
        if USER_STATS_FILE.exists():
            data = json.loads(USER_STATS_FILE.read_text(encoding="utf-8"))
            user_stats = {int(k): v for k, v in data.items()}
            logger.info("Loaded user stats for %s users", len(user_stats))
        else:
            user_stats = {}
    except Exception as exc:
        logger.error("Error loading user stats: %s", exc)
        user_stats = {}


def save_user_stats() -> None:
    try:
        data = {str(k): v for k, v in user_stats.items()}
        USER_STATS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.error("Error saving user stats: %s", exc)


def log_user_message(interaction: discord.Interaction, command: str, message_text: str = "") -> None:
    try:
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel

        file_exists = USER_MESSAGES_FILE.exists()

        row_data = [
            datetime.now().isoformat(),
            user.id,
            user.name,
            user.display_name,
            getattr(user, "discriminator", "0000"),
            guild.id if guild else "DM",
            guild.name if guild else "Direct Message",
            channel.id if channel else "DM",
            getattr(channel, "name", "DM"),
            command,
            message_text[:500],
        ]

        with USER_MESSAGES_FILE.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "timestamp",
                    "user_id",
                    "username",
                    "display_name",
                    "discriminator",
                    "guild_id",
                    "guild_name",
                    "channel_id",
                    "channel_name",
                    "command",
                    "message_text",
                ])
            writer.writerow(row_data)

    except Exception as exc:
        logger.error("Error logging user message: %s", exc)


def log_user_session(user_id: int, session_data: dict[str, Any]) -> None:
    try:
        sessions: dict[str, Any] = {}
        if USER_SESSIONS_FILE.exists():
            sessions = json.loads(USER_SESSIONS_FILE.read_text(encoding="utf-8"))

        user_key = str(user_id)
        sessions.setdefault(user_key, [])
        sessions[user_key].append({"timestamp": datetime.now().isoformat(), **session_data})
        sessions[user_key] = sessions[user_key][-50:]

        USER_SESSIONS_FILE.write_text(json.dumps(sessions, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.error("Error logging user session: %s", exc)


def get_user_safety_info(user_id: int) -> dict[str, Any]:
    try:
        sessions: dict[str, Any] = {}
        if USER_SESSIONS_FILE.exists():
            sessions = json.loads(USER_SESSIONS_FILE.read_text(encoding="utf-8"))

        user_sessions = sessions.get(str(user_id), [])
        return {
            "user_id": user_id,
            "stats": user_stats.get(user_id, {}),
            "recent_sessions": user_sessions[-10:],
            "total_sessions": len(user_sessions),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ============================================================
# API HELPERS
# ============================================================

async def fetch_json(endpoint: str, params: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    url = f"{CHECHEN_API_URL}{endpoint}"

    try:
        async with aiohttp.ClientSession(timeout=API_TIMEOUT) as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()

                logger.warning("API returned HTTP %s for %s", response.status, response.url)
                return None

    except asyncio.TimeoutError:
        logger.error("API timeout: %s", url)
        return None
    except Exception as exc:
        logger.error("API error for %s: %s", url, exc)
        return None


async def search_api(query: str, lang: str = "all", limit: int = 5, offset: int = 0) -> Optional[dict[str, Any]]:
    return await fetch_json(
        "/search",
        params={"q": query, "lang": lang, "limit": limit, "offset": offset},
    )


async def random_api() -> Optional[dict[str, Any]]:
    return await fetch_json("/random")


async def stats_api() -> Optional[dict[str, Any]]:
    return await fetch_json("/stats")


async def transliterate_api(text: str) -> Optional[dict[str, Any]]:
    return await fetch_json("/transliterate", params={"text": text})


async def categories_api() -> Optional[dict[str, Any]]:
    data = await fetch_json("/categories")
    if data:
        return data

    # Fallback for app.py versions that only expose /stats.
    stats = await stats_api()
    if not stats:
        return None

    categories = stats.get("top_categories") or stats.get("category_breakdown") or {}
    return {
        "categories": categories,
        "total_categories": len(categories),
    }


async def category_api(category_name: str, limit: int = 10) -> Optional[dict[str, Any]]:
    # Try native endpoint first.
    data = await fetch_json(f"/category/{quote(category_name)}")
    if data:
        return data

    # Fallback: search category name.
    search = await search_api(category_name, "all", limit)
    if not search:
        return None

    return {
        "category": category_name,
        "count": search.get("total", search.get("count", 0)),
        "words": search.get("results", []),
    }


# ============================================================
# STATS HELPERS
# ============================================================

def get_user_stats(user_id: int) -> dict[str, Any]:
    if user_id not in user_stats:
        user_stats[user_id] = {
            "current_streak": 0,
            "best_streak": 0,
            "total_correct": 0,
            "total_questions": 0,
            "last_quiz_date": None,
            "first_seen": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "total_commands": 0,
        }
        save_user_stats()

    user_stats[user_id]["last_active"] = datetime.now().isoformat()
    return user_stats[user_id]


def update_user_streak(user_id: int, is_correct: bool) -> dict[str, Any]:
    stats = get_user_stats(user_id)
    stats["total_questions"] += 1

    if is_correct:
        stats["current_streak"] += 1
        stats["total_correct"] += 1
        stats["best_streak"] = max(stats["best_streak"], stats["current_streak"])
    else:
        stats["current_streak"] = 0

    stats["last_quiz_date"] = datetime.now().isoformat()
    save_user_stats()

    accuracy = (stats["total_correct"] / max(stats["total_questions"], 1)) * 100
    log_user_session(
        user_id,
        {
            "action": "quiz_answer",
            "correct": is_correct,
            "current_streak": stats["current_streak"],
            "accuracy": accuracy,
        },
    )

    return stats


def track_command_usage(interaction: discord.Interaction, command_name: str, message_text: str = "") -> None:
    user_id = interaction.user.id
    stats = get_user_stats(user_id)
    stats["total_commands"] += 1

    log_user_message(interaction, command_name, message_text)
    log_user_session(
        user_id,
        {
            "action": "command_used",
            "command": command_name,
            "total_commands": stats["total_commands"],
        },
    )

    save_user_stats()


# ============================================================
# PREMIUM DISPLAY HELPERS
# ============================================================

def safe_text(value: Any, fallback: str = "—") -> str:
    text = "" if value is None else str(value).strip()
    return text if text else fallback


def cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def premium_embed(
    title: str,
    *,
    description: Optional[str] = None,
    color: int = COLOR_PRIMARY,
    interaction: Optional[discord.Interaction] = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(),
    )

    embed.set_author(name=BRAND_NAME, icon_url=bot.user.display_avatar.url if bot.user else None)

    footer = BRAND_FOOTER
    if interaction:
        footer += f" • requested by {interaction.user.display_name}"

    embed.set_footer(text=footer)

    return embed


def word_title(word: dict[str, Any]) -> str:
    chechen = safe_text(word.get("chechen_word"))
    latin = safe_text(word.get("chechen_latin"), "")

    if latin:
        return f"{chechen}  •  {latin}"

    return chechen


def word_summary_lines(word: dict[str, Any], *, include_example: bool = True) -> str:
    """Compact premium dictionary card.

    Shows only the useful info:
    - Chechen Cyrillic + Latin
    - Russian Cyrillic + Latin
    - English
    - Optional example
    No category/type noise.
    """
    chechen = safe_text(word.get("chechen_word"))
    chechen_latin = safe_text(word.get("chechen_latin"), "")
    russian = safe_text(word.get("russian_translation"), "")
    russian_latin = safe_text(word.get("russian_latin"), "")
    english = safe_text(word.get("english_translation"), "")

    lines = []

    # Main word line
    if chechen_latin:
        lines.append(f"**{chechen}**  ·  `{chechen_latin}`")
    else:
        lines.append(f"**{chechen}**")

    # Translation lines
    if russian or russian_latin:
        if russian and russian_latin:
            lines.append(f"🇷🇺 {russian}  ·  `{russian_latin}`")
        elif russian:
            lines.append(f"🇷🇺 {russian}")
        else:
            lines.append(f"🇷🇺 `{russian_latin}`")

    if english:
        lines.append(f"🇺🇸 {english}")

    # Optional example, but keep it short.
    example_chechen = safe_text(word.get("example_chechen"), "")
    example_chechen_latin = safe_text(word.get("example_chechen_latin"), "")
    example_english = safe_text(word.get("example_english"), "")

    if include_example and (example_chechen or example_english):
        example_parts = []
        if example_chechen:
            example_parts.append(f"“{example_chechen}”")
        if example_chechen_latin:
            example_parts.append(f"`{example_chechen_latin}`")
        if example_english:
            example_parts.append(f"→ {example_english}")

        lines.append("💬 " + "  ".join(example_parts))

    return cut("\n".join(lines), 650)


def compact_word_line(word: dict[str, Any]) -> str:
    chechen = safe_text(word.get("chechen_word"))
    latin = safe_text(word.get("chechen_latin"), "")
    english = safe_text(word.get("english_translation"), "")
    russian = safe_text(word.get("russian_translation"), "")
    russian_latin = safe_text(word.get("russian_latin"), "")

    title = f"**{chechen}**"
    if latin:
        title += f" · `{latin}`"

    parts = []
    if russian:
        parts.append(f"🇷🇺 {russian}")
    if russian_latin:
        parts.append(f"`{russian_latin}`")
    if english:
        parts.append(f"🇺🇸 {english}")

    return cut(f"{title}\n" + " · ".join(parts), 300)


def get_main_translation(word: dict[str, Any]) -> str:
    return safe_text(word.get("english_translation"), safe_text(word.get("russian_translation"), ""))


def normalize_answer(value: str) -> str:
    return value.strip().casefold()


def is_answer_correct(user_answer: str, word: dict[str, Any]) -> bool:
    answer = normalize_answer(user_answer)
    accepted = {
        normalize_answer(word.get("english_translation", "")),
        normalize_answer(word.get("russian_translation", "")),
        normalize_answer(word.get("chechen_word", "")),
        normalize_answer(word.get("chechen_latin", "")),
        normalize_answer(word.get("russian_latin", "")),
    }
    accepted = {x for x in accepted if x}

    if answer in accepted:
        return True

    return any(answer in x or x in answer for x in accepted if len(x) >= 3)


async def send_api_down(interaction: discord.Interaction) -> None:
    embed = premium_embed(
        "API offline",
        description=(
            "I could not reach the local dictionary API.\n\n"
            "**Start it first:**\n"
            "`python app.py`\n\n"
            f"Configured API URL: `{CHECHEN_API_URL}`"
        ),
        color=COLOR_RED,
        interaction=interaction,
    )
    await interaction.followup.send(embed=embed)


def get_multiple_choice_options(correct_word: dict[str, Any], all_words: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    correct_value = normalize_answer(get_main_translation(correct_word))

    available = [
        w for w in all_words
        if normalize_answer(get_main_translation(w)) != correct_value
        and get_main_translation(w).strip()
    ]

    if len(available) < 3:
        return None

    options = [correct_word] + random.sample(available, 3)
    random.shuffle(options)

    correct_index = options.index(correct_word)

    return {
        "options": options,
        "correct_index": correct_index,
        "correct_letter": chr(65 + correct_index),
    }


# ============================================================
# DISCORD UI
# ============================================================

class SearchResultsView(discord.ui.View):
    def __init__(self, *, query: str, lang: str, total: int, offset: int = 0, limit: int = 3):
        super().__init__(timeout=120)
        self.query = query
        self.lang = lang
        self.total = total
        self.offset = offset
        self.limit = limit
        self._update_button_state()

    def _update_button_state(self) -> None:
        self.previous_button.disabled = self.offset <= 0
        self.next_button.disabled = self.offset + self.limit >= self.total

    async def build_embed(self, interaction: discord.Interaction) -> Optional[discord.Embed]:
        data = await search_api(self.query, self.lang, self.limit, self.offset)
        if not data:
            return None

        results = data.get("results", [])
        self.total = int(data.get("total", data.get("count", 0)))
        self._update_button_state()

        embed = premium_embed(
            f"{ICON_SEARCH} {self.query}",
            description=(
                f"`{self.total}` result(s) • page `{self.offset // self.limit + 1}` • mode `{self.lang}`"
            ),
            color=COLOR_PRIMARY,
            interaction=interaction,
        )

        for index, word in enumerate(results, start=self.offset + 1):
            embed.add_field(
                name=cut(f"{index}. {word_title(word)}", 256),
                value=word_summary_lines(word, include_example=True),
                inline=False,
            )

        if not results:
            embed.description = "No results found."

        return embed

    @discord.ui.button(label="Previous", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.offset = max(0, self.offset - self.limit)
        embed = await self.build_embed(interaction)
        if embed is None:
            await interaction.response.send_message("API is offline.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.offset += self.limit
        embed = await self.build_embed(interaction)
        if embed is None:
            await interaction.response.send_message("API is offline.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=embed, view=self)


# ============================================================
# BOT EVENTS
# ============================================================

@bot.event
async def on_ready() -> None:
    load_user_stats()

    print(f"✅ {bot.user} is online")
    print(f"📡 API URL: {CHECHEN_API_URL}")
    print(f"📂 Data directory: {DATA_DIR}")
    print(f"📊 Loaded stats for {len(user_stats)} users")

    try:
        print("🔄 Syncing slash commands...")

        if TEST_GUILD_ID:
            guild = discord.Object(id=TEST_GUILD_ID)
            tree.copy_global_to(guild=guild)
            synced = await tree.sync(guild=guild)
            print(f"✅ Synced {len(synced)} slash commands to test guild {TEST_GUILD_ID}")
        else:
            synced = await tree.sync()
            print(f"✅ Synced {len(synced)} slash commands globally")
            print("⏳ Global slash commands can take up to 1 hour to appear")

        print("📋 Commands:", ", ".join(cmd.name for cmd in synced))

    except Exception as exc:
        logger.exception("Failed to sync commands: %s", exc)


# ============================================================
# SLASH COMMANDS
# ============================================================

@tree.command(name="chechen", description="Premium search: Chechen, Latin, Russian, or English")
@app_commands.describe(
    word="Word or phrase to search. Supports Cyrillic, Noxçiy Latin, Russian, Russian Latin, English.",
    mode="Search mode. Auto is recommended.",
)
@app_commands.choices(mode=SEARCH_MODE_CHOICES)
async def chechen(
    interaction: discord.Interaction,
    word: str,
    mode: Optional[app_commands.Choice[str]] = None,
):
    await interaction.response.defer()
    track_command_usage(interaction, "chechen", word)

    lang = mode.value if mode else "all"
    data = await search_api(word, lang, limit=3, offset=0)

    if data is None:
        await send_api_down(interaction)
        return

    total = int(data.get("total", data.get("count", 0)))
    results = data.get("results", [])

    if total == 0 or not results:
        embed = premium_embed(
            "No results found",
            description=(
                f"I could not find anything for `{word}`.\n\n"
                "Try a different spelling, Cyrillic, Latin, Russian, or English."
            ),
            color=COLOR_RED,
            interaction=interaction,
        )
        await interaction.followup.send(embed=embed)
        return

    view = SearchResultsView(query=word, lang=lang, total=total, offset=0, limit=3)
    embed = await view.build_embed(interaction)

    await interaction.followup.send(embed=embed, view=view)


@tree.command(name="transliterate", description="Convert Cyrillic Chechen/Russian into Noxçiy Abat Latin")
@app_commands.describe(text="Cyrillic text, for example: хьо, къамел, цӀога")
async def transliterate(interaction: discord.Interaction, text: str):
    await interaction.response.defer()
    track_command_usage(interaction, "transliterate", text)

    data = await transliterate_api(text)

    if data is None:
        await send_api_down(interaction)
        return

    embed = premium_embed(
        f"{ICON_LATIN} Noxçiy Abat Transliteration",
        color=COLOR_BLUE,
        interaction=interaction,
    )

    embed.add_field(name="Original", value=f"`{safe_text(data.get('text'))}`", inline=False)
    embed.add_field(name="Noxçiy Abat", value=f"`{safe_text(data.get('latin'))}`", inline=False)
    embed.add_field(name="Easy ASCII fallback", value=f"`{safe_text(data.get('latin_ascii_fallback'))}`", inline=False)

    await interaction.followup.send(embed=embed)


@tree.command(name="random", description="Get a premium random Chechen dictionary entry")
async def random_word(interaction: discord.Interaction):
    await interaction.response.defer()
    track_command_usage(interaction, "random")

    data = await random_api()

    if not data:
        await send_api_down(interaction)
        return

    embed = premium_embed(
        f"{ICON_RANDOM} Random Chechen Word",
        color=COLOR_PURPLE,
        interaction=interaction,
    )

    embed.add_field(name=word_title(data), value=word_summary_lines(data), inline=False)

    await interaction.followup.send(embed=embed)


@tree.command(name="categories", description="Show available dictionary categories")
async def categories(interaction: discord.Interaction):
    await interaction.response.defer()
    track_command_usage(interaction, "categories")

    data = await categories_api()

    if not data:
        await send_api_down(interaction)
        return

    categories_data = data.get("categories", {})
    total = data.get("total_categories", len(categories_data))

    if not categories_data:
        embed = premium_embed(
            "No categories found",
            description="Your current API/database did not return category information.",
            color=COLOR_RED,
            interaction=interaction,
        )
        await interaction.followup.send(embed=embed)
        return

    sorted_categories = sorted(categories_data.items(), key=lambda x: x[1], reverse=True)[:20]

    lines = [
        f"`{i:02d}` **{name}** — {count:,} entries"
        for i, (name, count) in enumerate(sorted_categories, start=1)
    ]

    embed = premium_embed(
        f"{ICON_CATEGORY} Dictionary Categories",
        description="\n".join(lines),
        color=COLOR_BLUE,
        interaction=interaction,
    )

    embed.set_footer(text=f"{BRAND_FOOTER} • {total} categories")

    await interaction.followup.send(embed=embed)


@tree.command(name="category", description="Show words from a specific category")
@app_commands.describe(category_name="Example: imported_auto_translated, religion, basic")
async def category(interaction: discord.Interaction, category_name: str):
    await interaction.response.defer()
    track_command_usage(interaction, "category", category_name)

    data = await category_api(category_name, limit=10)

    if not data or int(data.get("count", 0)) == 0:
        embed = premium_embed(
            "No category results",
            description=f"No entries found for category/search `{category_name}`.",
            color=COLOR_RED,
            interaction=interaction,
        )
        await interaction.followup.send(embed=embed)
        return

    words = data.get("words") or data.get("results") or []
    embed = premium_embed(
        f"{ICON_CATEGORY} Category: {category_name}",
        description=f"Showing up to `{min(len(words), 10)}` entries.",
        color=COLOR_GOLD,
        interaction=interaction,
    )

    for word in words[:10]:
        embed.add_field(name=cut(word_title(word), 256), value=compact_word_line(word), inline=False)

    embed.set_footer(text=f"{BRAND_FOOTER} • total {data.get('count', len(words))} entries")

    await interaction.followup.send(embed=embed)


@tree.command(name="word_of_day", description="Get the Chechen word of the day")
async def word_of_day(interaction: discord.Interaction):
    await interaction.response.defer()
    track_command_usage(interaction, "word_of_day")

    current_date = datetime.now().strftime("%Y-%m-%d")
    seed_value = int(datetime.now().strftime("%Y%m%d"))
    random.seed(seed_value)

    # Fetch several random words and pick deterministically from the daily seed.
    candidates = []
    for _ in range(8):
        word = await random_api()
        if word:
            candidates.append(word)

    random.seed()

    if not candidates:
        await send_api_down(interaction)
        return

    word_data = random.choice(candidates)

    embed = premium_embed(
        "🌅 Chechen Word of the Day",
        description=f"Daily learning card for `{current_date}`.",
        color=COLOR_GOLD,
        interaction=interaction,
    )

    embed.add_field(name=word_title(word_data), value=word_summary_lines(word_data), inline=False)
    embed.set_footer(text=f"{BRAND_FOOTER} • same day, same vibe ✦")

    await interaction.followup.send(embed=embed)


@tree.command(name="statistics", description="Show premium dictionary statistics")
async def statistics(interaction: discord.Interaction):
    await interaction.response.defer()
    track_command_usage(interaction, "statistics")

    data = await stats_api()

    if not data:
        await send_api_down(interaction)
        return

    total_words = data.get("total_words", 0)
    latin_words = data.get("words_with_chechen_latin", 0)
    categories = data.get("top_categories") or data.get("category_breakdown") or {}
    total_categories = data.get("total_categories", len(categories))

    embed = premium_embed(
        f"{ICON_STATS} Dictionary Statistics",
        color=COLOR_BLUE,
        interaction=interaction,
    )

    embed.add_field(name="Total entries", value=f"**{int(total_words):,}**", inline=True)
    embed.add_field(name="Latin supported", value=f"**{int(latin_words or 0):,}**", inline=True)
    embed.add_field(name="Categories", value=f"**{int(total_categories or 0):,}**", inline=True)

    if categories:
        top = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:8]
        text = "\n".join(f"**{name}** — {count:,}" for name, count in top)
        embed.add_field(name="Top categories", value=text, inline=False)

    await interaction.followup.send(embed=embed)


@tree.command(name="batch_search", description="Search multiple words at once")
@app_commands.describe(words="Up to 8 words separated by spaces")
async def batch_search(interaction: discord.Interaction, words: str):
    await interaction.response.defer()
    track_command_usage(interaction, "batch_search", words)

    word_list = words.split()[:8]
    found = []

    for word in word_list:
        data = await search_api(word, "all", limit=1)
        if data and data.get("results"):
            found.append((word, data["results"][0]))

    if not found:
        embed = premium_embed(
            "No results",
            description="No results found for any of the searched words.",
            color=COLOR_RED,
            interaction=interaction,
        )
        await interaction.followup.send(embed=embed)
        return

    embed = premium_embed(
        "🔍 Batch Search",
        description=f"Found `{len(found)}` of `{len(word_list)}` searched words.",
        color=COLOR_GOLD,
        interaction=interaction,
    )

    for original, word in found:
        embed.add_field(
            name=cut(f"{original} → {word_title(word)}", 256),
            value=compact_word_line(word),
            inline=False,
        )

    await interaction.followup.send(embed=embed)


# ============================================================
# QUIZ COMMANDS
# ============================================================

@tree.command(name="quiz", description="Start a premium Chechen vocabulary quiz")
async def quiz(interaction: discord.Interaction):
    await interaction.response.defer()
    track_command_usage(interaction, "quiz")

    data = await random_api()

    if not data:
        await send_api_down(interaction)
        return

    user_id = interaction.user.id
    quiz_data[user_id] = {
        "word_data": data,
        "quiz_type": "text",
        "start_time": datetime.now().isoformat(),
    }

    stats = get_user_stats(user_id)

    embed = premium_embed(
        "🧠 Vocabulary Quiz",
        description=(
            f"What does **{safe_text(data.get('chechen_word'))}** "
            f"`/{safe_text(data.get('chechen_latin'), '')}/` mean?\n\n"
            "Answer with English, Russian, Chechen, or Latin."
        ),
        color=COLOR_PURPLE,
        interaction=interaction,
    )

    if stats["current_streak"] > 0:
        embed.add_field(name="Current streak", value=f"🔥 **{stats['current_streak']}**", inline=True)

    embed.set_footer(text=f"{BRAND_FOOTER} • use /answer")

    await interaction.followup.send(embed=embed)


@tree.command(name="quiz_mc", description="Start a premium multiple choice quiz")
async def quiz_mc(interaction: discord.Interaction):
    await interaction.response.defer()
    track_command_usage(interaction, "quiz_mc")

    all_words = []

    for _ in range(8):
        word = await random_api()
        if word and get_main_translation(word).strip():
            all_words.append(word)

    if len(all_words) < 4:
        embed = premium_embed(
            "Quiz unavailable",
            description="Could not fetch enough quiz words. Try again.",
            color=COLOR_RED,
            interaction=interaction,
        )
        await interaction.followup.send(embed=embed)
        return

    correct = all_words[0]
    options = get_multiple_choice_options(correct, all_words[1:])

    if not options:
        embed = premium_embed(
            "Quiz unavailable",
            description="Could not generate multiple-choice options. Try `/quiz`.",
            color=COLOR_RED,
            interaction=interaction,
        )
        await interaction.followup.send(embed=embed)
        return

    quiz_data[interaction.user.id] = {
        "word_data": correct,
        "quiz_type": "multiple_choice",
        "mc_options": options,
        "start_time": datetime.now().isoformat(),
    }

    letters = ["A", "B", "C", "D"]
    options_text = "\n".join(
        f"**{letters[i]})** {get_main_translation(option)}"
        for i, option in enumerate(options["options"])
    )

    embed = premium_embed(
        "🎯 Multiple Choice Quiz",
        description=(
            f"What does **{safe_text(correct.get('chechen_word'))}** "
            f"`/{safe_text(correct.get('chechen_latin'), '')}/` mean?"
        ),
        color=COLOR_PURPLE,
        interaction=interaction,
    )

    embed.add_field(name="Options", value=options_text, inline=False)
    embed.set_footer(text=f"{BRAND_FOOTER} • answer with /answer A, B, C, or D")

    await interaction.followup.send(embed=embed)


@tree.command(name="answer", description="Submit your quiz answer or reveal the answer")
@app_commands.describe(your_answer="Your answer. For multiple choice: A, B, C, or D.")
async def answer(interaction: discord.Interaction, your_answer: Optional[str] = None):
    await interaction.response.defer()
    track_command_usage(interaction, "answer", your_answer or "")

    user_id = interaction.user.id

    if user_id not in quiz_data:
        embed = premium_embed(
            "No active quiz",
            description="Start with `/quiz` or `/quiz_mc` first.",
            color=COLOR_RED,
            interaction=interaction,
        )
        await interaction.followup.send(embed=embed)
        return

    quiz_info = quiz_data[user_id]
    word = quiz_info["word_data"]
    quiz_type = quiz_info.get("quiz_type", "text")

    is_correct = False
    submitted = bool(your_answer)

    if submitted and quiz_type == "multiple_choice":
        options = quiz_info["mc_options"]
        correct_letter = options["correct_letter"].casefold()
        submitted_letter = your_answer.strip().casefold()

        if submitted_letter not in {"a", "b", "c", "d"}:
            embed = premium_embed(
                "Invalid answer",
                description="Please answer with **A**, **B**, **C**, or **D**.",
                color=COLOR_RED,
                interaction=interaction,
            )
            await interaction.followup.send(embed=embed)
            return

        is_correct = submitted_letter == correct_letter

    elif submitted:
        is_correct = is_answer_correct(your_answer, word)

    if submitted:
        stats = update_user_streak(user_id, is_correct)
        title = "🎉 Correct" if is_correct else "❌ Incorrect"
        color = COLOR_PRIMARY if is_correct else COLOR_RED
    else:
        stats = get_user_stats(user_id)
        title = "✅ Quiz Answer"
        color = COLOR_BLUE

    embed = premium_embed(title, color=color, interaction=interaction)
    embed.add_field(name=word_title(word), value=word_summary_lines(word), inline=False)

    if submitted:
        embed.add_field(name="Your answer", value=f"`{your_answer}`", inline=True)
        embed.add_field(name="Current streak", value=f"🔥 **{stats['current_streak']}**", inline=True)
        embed.add_field(name="Best streak", value=f"🏆 **{stats['best_streak']}**", inline=True)

    del quiz_data[user_id]

    await interaction.followup.send(embed=embed)


@tree.command(name="my_stats", description="View your premium learning statistics")
async def my_stats(interaction: discord.Interaction):
    await interaction.response.defer()
    track_command_usage(interaction, "my_stats")

    stats = get_user_stats(interaction.user.id)

    embed = premium_embed(
        "📈 Your Learning Profile",
        color=COLOR_BLUE,
        interaction=interaction,
    )

    if stats["total_questions"] == 0:
        embed.description = "You have not answered any quiz questions yet.\nStart with `/quiz` or `/quiz_mc`."
        await interaction.followup.send(embed=embed)
        return

    accuracy = (stats["total_correct"] / max(stats["total_questions"], 1)) * 100

    embed.add_field(name="Current streak", value=f"🔥 **{stats['current_streak']}**", inline=True)
    embed.add_field(name="Best streak", value=f"🏆 **{stats['best_streak']}**", inline=True)
    embed.add_field(name="Accuracy", value=f"🎯 **{accuracy:.1f}%**", inline=True)
    embed.add_field(name="Correct answers", value=f"✅ **{stats['total_correct']}**", inline=True)
    embed.add_field(name="Total questions", value=f"🧠 **{stats['total_questions']}**", inline=True)
    embed.add_field(name="Commands used", value=f"⚡ **{stats['total_commands']}**", inline=True)

    if stats["current_streak"] >= 10:
        embed.add_field(name="Status", value="🌟 Elite streak. Keep going.", inline=False)
    elif stats["current_streak"] >= 5:
        embed.add_field(name="Status", value="🔥 Strong momentum.", inline=False)
    elif accuracy >= 80:
        embed.add_field(name="Status", value="✨ Clean accuracy. Nice work.", inline=False)

    await interaction.followup.send(embed=embed)


@tree.command(name="pronunciation", description="Show pronunciation and Noxçiy Abat Latin for a word")
async def pronunciation(interaction: discord.Interaction, word: str):
    await interaction.response.defer()
    track_command_usage(interaction, "pronunciation", word)

    data = await search_api(word, "all", limit=1)

    if not data or not data.get("results"):
        embed = premium_embed(
            "No pronunciation found",
            description=f"No result found for `{word}`.",
            color=COLOR_RED,
            interaction=interaction,
        )
        await interaction.followup.send(embed=embed)
        return

    result = data["results"][0]

    embed = premium_embed(
        "🗣️ Pronunciation Guide",
        color=COLOR_PURPLE,
        interaction=interaction,
    )

    embed.add_field(name="Chechen", value=f"`{safe_text(result.get('chechen_word'))}`", inline=False)
    embed.add_field(name="Noxçiy Abat", value=f"`{safe_text(result.get('chechen_latin'), safe_text(result.get('pronunciation')) )}`", inline=False)

    if result.get("pronunciation"):
        embed.add_field(name="Stored pronunciation", value=f"`{result['pronunciation']}`", inline=False)

    embed.add_field(name="Meaning", value=safe_text(result.get("english_translation")), inline=False)

    await interaction.followup.send(embed=embed)


# ============================================================
# ADMIN COMMANDS
# ============================================================

@tree.command(name="user_info", description="Get user safety information (admin only)")
async def user_info(interaction: discord.Interaction, user_id: str):
    await interaction.response.defer(ephemeral=True)
    track_command_usage(interaction, "user_info", user_id)

    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.followup.send("This command is for administrators only.", ephemeral=True)
        return

    try:
        target_user_id = int(user_id)
    except ValueError:
        await interaction.followup.send("Invalid user ID format.", ephemeral=True)
        return

    info = get_user_safety_info(target_user_id)

    if "error" in info:
        await interaction.followup.send(f"Error: {info['error']}", ephemeral=True)
        return

    stats = info.get("stats", {})

    embed = premium_embed("🔍 User Safety Information", color=COLOR_BLUE)
    embed.add_field(name="User ID", value=str(target_user_id), inline=True)
    embed.add_field(name="Total commands", value=str(stats.get("total_commands", 0)), inline=True)
    embed.add_field(name="Total sessions", value=str(info.get("total_sessions", 0)), inline=True)
    embed.add_field(name="Best streak", value=str(stats.get("best_streak", 0)), inline=True)
    embed.add_field(name="First seen", value=str(stats.get("first_seen", "Unknown"))[:16], inline=True)
    embed.add_field(name="Last active", value=str(stats.get("last_active", "Unknown"))[:16], inline=True)

    recent = info.get("recent_sessions", [])[-5:]
    if recent:
        recent_text = "\n".join(
            f"• {session.get('timestamp', '')[:16]} — {session.get('action', 'Unknown')}"
            for session in recent
        )
        embed.add_field(name="Recent activity", value=recent_text, inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(name="export_data", description="Show bot usage analytics (admin only)")
async def export_data(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    track_command_usage(interaction, "export_data")

    if interaction.user.id not in ADMIN_USER_IDS:
        await interaction.followup.send("This command is for administrators only.", ephemeral=True)
        return

    total_users = len(user_stats)
    total_questions = sum(stats.get("total_questions", 0) for stats in user_stats.values())
    total_correct = sum(stats.get("total_correct", 0) for stats in user_stats.values())
    avg_accuracy = (total_correct / max(total_questions, 1)) * 100

    week_ago = datetime.now() - timedelta(days=7)
    active_users = 0

    for stats in user_stats.values():
        try:
            if datetime.fromisoformat(stats.get("last_active", "")) > week_ago:
                active_users += 1
        except Exception:
            pass

    embed = premium_embed("📈 Bot Usage Analytics", color=COLOR_BLUE)
    embed.add_field(name="Total users", value=str(total_users), inline=True)
    embed.add_field(name="Active users, 7 days", value=str(active_users), inline=True)
    embed.add_field(name="Quiz questions", value=str(total_questions), inline=True)
    embed.add_field(name="Correct answers", value=str(total_correct), inline=True)
    embed.add_field(name="Average accuracy", value=f"{avg_accuracy:.1f}%", inline=True)
    embed.add_field(name="Data directory", value=f"`{DATA_DIR}`", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(name="help", description="Show premium bot commands")
async def help_command(interaction: discord.Interaction):
    await interaction.response.defer()
    track_command_usage(interaction, "help")

    embed = premium_embed(
        "📚 NoxchoDictionary Commands",
        description=(
            "A compact premium Chechen dictionary experience with Cyrillic, "
            "**Noxçiy Abat Latin**, Russian, and English support."
        ),
        color=COLOR_DARK,
        interaction=interaction,
    )

    embed.add_field(
        name="Dictionary",
        value=(
            "`/chechen word:<text>` — premium search\n"
            "`/random` — random entry\n"
            "`/word_of_day` — daily word\n"
            "`/categories` — category overview\n"
            "`/category` — category/search listing\n"
            "`/statistics` — dictionary stats"
        ),
        inline=False,
    )

    embed.add_field(
        name="Noxçiy Abat",
        value=(
            "`/transliterate text:<text>` — Cyrillic → Noxçiy Latin\n"
            "`/pronunciation word:<text>` — pronunciation card\n"
            "`/batch_search words:<text>` — search multiple words"
        ),
        inline=False,
    )

    embed.add_field(
        name="Learning",
        value=(
            "`/quiz` — text quiz\n"
            "`/quiz_mc` — multiple-choice quiz\n"
            "`/answer` — answer or reveal\n"
            "`/my_stats` — personal learning profile"
        ),
        inline=False,
    )

    if interaction.user.id in ADMIN_USER_IDS:
        embed.add_field(
            name="Admin",
            value="`/user_info` — user safety info\n`/export_data` — analytics",
            inline=False,
        )

    await interaction.followup.send(embed=embed)


# ============================================================
# RUN BOT
# ============================================================

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN not found.")
        print(f"Create .env here: {DEFAULT_ENV_PATH}")
        print("Example:")
        print("DISCORD_TOKEN=your_token_here")
        print("API_URL=http://127.0.0.1:27016")
        raise SystemExit(1)

    try:
        print("🚀 Starting NoxchoDictionary Premium Bot...")
        print(f"📡 API URL: {CHECHEN_API_URL}")
        print(f"📂 Data directory: {DATA_DIR}")

        load_user_stats()
        bot.run(DISCORD_TOKEN)

    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user.")
    except discord.LoginFailure:
        print("❌ Invalid Discord token. Check DISCORD_TOKEN in .env.")
    except discord.PrivilegedIntentsRequired:
        print("❌ Enable Message Content Intent in the Discord Developer Portal.")
    except Exception as exc:
        logger.exception("Failed to start bot: %s", exc)
        print(f"❌ Failed to start bot: {exc}")
    finally:
        save_user_stats()
        print("💾 User data saved.")
