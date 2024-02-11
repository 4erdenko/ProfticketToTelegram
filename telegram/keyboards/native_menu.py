from aiogram import Bot
from aiogram.types import BotCommand

from telegram.lexicon.lexicon_ru import LEXICON_NATIVE_COMMANDS_RU


async def set_native_menu(bot: Bot):
    main_menu_commands = [
        BotCommand(command=command, description=description)
        for command, description in LEXICON_NATIVE_COMMANDS_RU.items()
    ]
    await bot.set_my_commands(main_menu_commands)
