from pathlib import Path

from tests.runtime_helpers import run_runtime_script


def test_runtime_imports_with_real_dependencies(tmp_path: Path) -> None:
    run_runtime_script(
        """
import asyncio

import main
from config import settings
from services.ermolova import ErmolovaInfo
from services.profticket.utils import pluralize

assert callable(main.main)
assert settings.SCHEDULE_SOURCE == 'ermolova'
assert pluralize('спектакль', 1) == 'спектакль'
assert pluralize('спектакль', 2) == 'спектакля'
assert pluralize('спектакль', 5) == 'спектаклей'

async def check_clients():
    source = ErmolovaInfo()
    await source.aclose()

asyncio.run(check_clients())
""",
        tmp_path,
    )
