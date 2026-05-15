import os
import requests
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
API_URL = os.getenv("API_URL", "http://127.0.0.1:27016")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN fehlt. Erstelle eine .env Datei mit deinem Bot Token.")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def search_dictionary(query: str, lang: str = "all", limit: int = 5):
    response = requests.get(
        f"{API_URL}/search",
        params={"q": query, "lang": lang, "limit": limit},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def format_word_short(word: dict) -> str:
    chechen = word.get("chechen_word", "")
    chechen_latin = word.get("chechen_latin", "")
    russian = word.get("russian_translation", "")
    russian_latin = word.get("russian_latin", "")
    english = word.get("english_translation", "")
    category = word.get("category", "")

    return (
        f"**Chechen:** {chechen}\n"
        f"**Latin:** {chechen_latin}\n"
        f"**Russian:** {russian}\n"
        f"**Russian Latin:** {russian_latin}\n"
        f"**English:** {english}\n"
        f"**Category:** {category}"
    )


@bot.event
async def on_ready():
    print(f"✅ Bot ist online als {bot.user}")


@bot.command(name="translate", aliases=["t", "tr"])
async def translate(ctx, *, query: str):
    try:
        data = search_dictionary(query, "all", 5)
    except requests.exceptions.RequestException:
        await ctx.reply("❌ API ist nicht erreichbar. Starte zuerst `python app.py`.")
        return

    results = data.get("results", [])

    if not results:
        await ctx.reply(f"❌ Keine Ergebnisse gefunden für: `{query}`")
        return

    embed = discord.Embed(
        title=f"🔎 Results for: {query}",
        description=f"Found total: {data.get('total', len(results))}",
        color=0x2ECC71,
    )

    for word in results[:5]:
        title = word.get("chechen_word", "") or "Result"
        latin = word.get("chechen_latin", "")

        embed.add_field(
            name=f"{title} / {latin}"[:256],
            value=format_word_short(word)[:1024],
            inline=False,
        )

    await ctx.reply(embed=embed)


@bot.command(name="latin")
async def latin(ctx, *, query: str):
    await search_by_lang(ctx, query, "latin")


@bot.command(name="chechen")
async def chechen(ctx, *, query: str):
    await search_by_lang(ctx, query, "chechen")


@bot.command(name="chechenlatin", aliases=["cl"])
async def chechen_latin(ctx, *, query: str):
    await search_by_lang(ctx, query, "chechen_latin")


@bot.command(name="russian")
async def russian(ctx, *, query: str):
    await search_by_lang(ctx, query, "russian")


@bot.command(name="russianlatin", aliases=["rl"])
async def russian_latin(ctx, *, query: str):
    await search_by_lang(ctx, query, "russian_latin")


@bot.command(name="english")
async def english(ctx, *, query: str):
    await search_by_lang(ctx, query, "english")


async def search_by_lang(ctx, query: str, lang: str):
    try:
        data = search_dictionary(query, lang, 5)
    except requests.exceptions.RequestException:
        await ctx.reply("❌ API ist nicht erreichbar. Starte zuerst `python app.py`.")
        return

    results = data.get("results", [])

    if not results:
        await ctx.reply(f"❌ Keine Ergebnisse gefunden für `{query}` in `{lang}`.")
        return

    lines = []
    for word in results[:5]:
        lines.append(format_word_short(word))

    await ctx.reply("\n\n".join(lines)[:1900])


@bot.command(name="randomword", aliases=["rw"])
async def randomword(ctx):
    try:
        response = requests.get(f"{API_URL}/random", timeout=15)
        response.raise_for_status()
        word = response.json()
    except requests.exceptions.RequestException:
        await ctx.reply("❌ API ist nicht erreichbar. Starte zuerst `python app.py`.")
        return

    await ctx.reply("🎲 **Random word**\n\n" + format_word_short(word))


@bot.command(name="dictstats")
async def dictstats(ctx):
    try:
        response = requests.get(f"{API_URL}/stats", timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException:
        await ctx.reply("❌ API ist nicht erreichbar. Starte zuerst `python app.py`.")
        return

    await ctx.reply(
        f"📊 **Dictionary Stats**\n"
        f"Total words: **{data.get('total_words', 0)}**\n"
        f"Words with Latin: **{data.get('words_with_chechen_latin', 0)}**"
    )


@bot.command(name="translit")
async def translit(ctx, *, text: str):
    try:
        response = requests.get(
            f"{API_URL}/transliterate",
            params={"text": text},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException:
        await ctx.reply("❌ API ist nicht erreichbar. Starte zuerst `python app.py`.")
        return

    await ctx.reply(
        f"**Original:** {data.get('text', '')}\n"
        f"**Noxçiy Latin:** {data.get('latin', '')}\n"
        f"**ASCII fallback:** {data.get('latin_ascii_fallback', '')}"
    )


bot.run(TOKEN)
