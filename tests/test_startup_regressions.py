from pathlib import Path

from tests.runtime_helpers import run_runtime_script


def test_optional_notifications_do_not_interrupt_lifecycle(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        """
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.utils import startup

async def check():
    bot = SimpleNamespace(
        delete_webhook=AsyncMock(),
        send_message=AsyncMock(side_effect=RuntimeError('unavailable admin')),
        session=SimpleNamespace(close=AsyncMock()),
    )
    with patch.object(
        startup, 'set_native_menu',
        AsyncMock(side_effect=RuntimeError('unavailable menu')),
    ):
        await startup.on_startup(bot, 1)
    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
    task = asyncio.create_task(asyncio.Event().wait())
    await startup.on_shutdown(bot, 1, task)
    assert task.cancelled()
    bot.session.close.assert_awaited_once()

    async def fail():
        raise RuntimeError('background update failed')

    failed_task = asyncio.create_task(fail())
    await asyncio.sleep(0)
    bot.session.close.reset_mock()
    await startup.on_shutdown(bot, 1, failed_task)
    bot.session.close.assert_awaited_once()

    bot.delete_webhook.side_effect = RuntimeError('webhook error')
    with patch.object(startup, 'set_native_menu', AsyncMock()) as menu:
        try:
            await startup.on_startup(bot, 1)
        except RuntimeError as error:
            assert str(error) == 'webhook error'
        else:
            raise AssertionError('Mandatory startup errors must propagate')
        menu.assert_not_awaited()

asyncio.run(check())
""",
        tmp_path,
    )


def test_production_token_uses_normalized_settings(tmp_path: Path) -> None:
    run_runtime_script(
        """
from telegram.utils import startup

for value in ('true', 'TRUE', '1', 'yes', 'on'):
    startup.settings.IN_DOCKER = value
    assert startup.get_token() == startup.settings.BOT_TOKEN
for value in ('false', '0', 'off'):
    startup.settings.IN_DOCKER = value
    assert startup.get_token() == startup.settings.TEST_BOT_TOKEN
""",
        tmp_path,
    )


def test_main_closes_http_clients_and_database_on_polling_failure(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        """
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import main

async def check():
    engine = SimpleNamespace(dispose=AsyncMock())
    source = SimpleNamespace(client=SimpleNamespace(aclose=AsyncMock()))
    bot = SimpleNamespace(
        send_message=AsyncMock(), session=SimpleNamespace(close=AsyncMock()),
    )
    dispatcher = SimpleNamespace(
        update=SimpleNamespace(middleware=lambda middleware: None),
        start_polling=AsyncMock(side_effect=RuntimeError('polling failed')),
    )
    update_task = None

    async def update_loop():
        nonlocal update_task
        update_task = asyncio.current_task()
        await asyncio.Event().wait()

    async def start_polling(bot):
        await asyncio.sleep(0)
        raise RuntimeError('polling failed')

    dispatcher.start_polling.side_effect = start_polling
    main.settings.SCHEDULE_SOURCE = 'profticket'
    with (
        patch.object(main, 'Bot', return_value=bot),
        patch.object(main, 'setup_logging'),
        patch.object(main, 'setup_dispatcher', AsyncMock(return_value=dispatcher)),
        patch.object(main, 'setup_database', AsyncMock(return_value=(None, {'engine': engine}))),
        patch.object(main, 'ProfticketsInfo', return_value=source),
        patch.object(main, 'ShowUpdateService', return_value=SimpleNamespace(update_loop=update_loop)),
        patch.object(main, 'on_startup', AsyncMock()),
    ):
        try:
            await main.main()
        except RuntimeError as error:
            assert str(error) == 'polling failed'
        else:
            raise AssertionError('Polling errors must propagate')
    assert update_task is not None and update_task.cancelled()
    bot.session.close.assert_awaited_once()
    source.client.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()

asyncio.run(check())
""",
        tmp_path,
    )
