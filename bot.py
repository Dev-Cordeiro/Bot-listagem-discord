import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from commands.item_control import ItemControl

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
APPLICATION_ID = int(os.getenv("DISCORD_APP_ID"))
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))

intents = discord.Intents.default()
intents.message_content = False

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    application_id=APPLICATION_ID
)

@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)
    bot.tree.clear_commands(guild=guild)
    bot.tree.clear_commands(guild=None)
    await bot.add_cog(ItemControl(bot))
    await bot.tree.sync(guild=guild)
    await bot.tree.sync()

@bot.event
async def on_ready():
    print(f"🤖 Bot iniciado como {bot.user} (ID {bot.user.id})")

if __name__ == "__main__":
    bot.run(TOKEN)
