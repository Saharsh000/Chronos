"""One-shot script: announces The Lab DLC and Economy v3 update in the study channel.
Run with:  python3 scripts/announce_lab_and_economy.py
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
            # Fallback fetch
            try:
                channel = await client.fetch_channel(CHANNEL_ID)
            except Exception as e:
                print(f"ERROR: could not fetch channel {CHANNEL_ID}: {e}")
                await client.close()
                return

        print(f"Logged in as {client.user}. Sending announcement to #{getattr(channel, 'name', CHANNEL_ID)}...")

        # 1. Plain @everyone ping in normal message
        await channel.send("@everyone 🧪 **The Lab DLC is LIVE + Massive Economy Overhaul!** Read the patch notes below:")
        
        # Slight pause so ping is cleanly delivered first
        await asyncio.sleep(1.5)

        # 2. Rich embed with full update details
        embed = discord.Embed(
            title="🧪 Chronos Major Update · The Lab & Economy v3",
            description=(
                "A brand new chapter of Chronos is here! Unlock **The Lab**, study Organic Chemistry "
                "to harvest elements, synthesize 500 compounds, and enjoy a freshly scaled server economy."
            ),
            color=0x00E676,
        )

        embed.add_field(
            name="🔬 The Lab & Organic Chemistry Mode",
            value=(
                "• **Unlock Requirement:** 30h all-time Chemistry study + **80,000 Chronocoins** (`.lab unlock`).\n"
                "• **OC Study Track:** Run `.start oc` (or `.start organic`) to roll 8 elemental precursors "
                "(`C, H, O, N, Cl, F, Br, I`) every credited minute.\n"
                "• **Compound Synthesis:** Synthesize compounds via `.synth <name or formula>`.\n"
                "• **Massive Compendium:** Browse **500 organic compounds** across 21 categories with `.compounds [category]` "
                "— complete with IUPAC formulas, condensed structures, and JEE-relevant facts.\n"
                "• **Prestige Rewards:** Unlock exclusive category master titles and hit milestones at 25, 50, 100, 200, 350, "
                "and 500 compounds to claim the **Grandmaster Chemist** title & 50,000 bonus coins!"
            ),
            inline=False,
        )

        embed.add_field(
            name="💰 Economy v3 Overhaul (Scaled for 50k+ Wallets)",
            value=(
                "• **Study Earning:** Doubled to **60 – 120 Chronocoins per minute** while studying.\n"
                "• **Commands Payouts:** `.work` now pays **3,500 – 8,000**, `.weekly` gives **40,000 – 80,000**, "
                "and `.beg` awards **400 – 1,200**.\n"
                "• **Daily & Streaks:** Base daily **4,500 – 9,000** + **300 coins/day** streak bonus (milestones up to 300,000 coins).\n"
                "• **Mystery Boxes:** Scaled rewards with jackpots up to **75,000 coins** + titles & streak freezes.\n"
                "• **Shop, Pets & Food:** Prices rebalanced to match the new higher earning rates."
            ),
            inline=False,
        )

        embed.add_field(
            name="🌐 Chronoweb Twin",
            value=(
                "Everything in The Lab is also available on the Chronoweb dashboard! Check your live element trays, "
                "synthesize with animated reaction flasks, and browse the interactive compendium."
            ),
            inline=False,
        )

        embed.set_footer(text="Chronos · The Lab DLC · Happy Studying & Synthesizing! ⚗️")

        await channel.send(embed=embed)
        print("Announcement successfully sent.")
        await client.close()

    await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
