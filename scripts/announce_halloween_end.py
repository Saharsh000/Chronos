"""One-shot script: announces the Halloween event wrap-up in the study channel.
Run with:  python3 scripts/announce_halloween_end.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import discord
from dotenv import load_dotenv

load_dotenv()

CHANNEL_ID = 1483042996059508836
TOKEN = os.getenv("DISCORD_TOKEN", "")


async def main() -> None:
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        channel = client.get_channel(CHANNEL_ID)
        if channel is None:
            print(f"ERROR: channel {CHANNEL_ID} not found")
            await client.close()
            return

        # 1. Plain @everyone ping
        await channel.send("@everyone 🎃 The Halloween event is over — read below!")

        # 2. Rich embed
        embed = discord.Embed(
            title="🎃 Halloween Event · Wrapped",
            description=(
                "The pumpkin patch has gone dark. No new boxes, candy, or pass progress "
                "are being earned from here on.\n\n"
                "**But your stash is safe — for 24 hours.**"
            ),
            color=0xFF7518,
        )
        embed.add_field(
            name="📦 What you can still do (until tomorrow)",
            value=(
                "• **Open** any Hallo-Boxes you're holding → `.openbox <tier>` or `.openbox all`\n"
                "• **Claim** unclaimed Jack-o'-Lantern pass rewards → `.pumpkin claim`\n"
                "• **Spend** your Candy in the shop → `.candyshop` / `.buycandy <item>`\n\n"
                "After the grace period the commands stay in the bot but drops are off and candy "
                "has nothing to buy — so open everything now."
            ),
            inline=False,
        )
        embed.add_field(
            name="🛒 Candy Shop reminder",
            value=(
                "🎃 **Pumpkaboo** (evolves → Gourgeist)\n"
                "🧪 **Inorganic Nightmare** title\n"
                "👻 **The Shift 1 Phantom** title\n"
                "⚡ **Sugar Rush** ×2 XP boost\n\n"
                "Check your balance with `.balance`."
            ),
            inline=False,
        )
        embed.add_field(
            name="✅ What stays permanently",
            value=(
                "Any pets, titles, food, Mystery Boxes, and Chronocoins you earned "
                "are yours forever. Only candy that goes unspent will just sit there."
            ),
            inline=False,
        )
        embed.set_footer(text="Thanks for grinding the patch 🕯️  · Chronos")

        await channel.send(embed=embed)
        print("Announcement sent.")
        await client.close()

    await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
