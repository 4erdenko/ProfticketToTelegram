import os
import subprocess
import sys
from pathlib import Path


def run_runtime_script(
    script: str,
    working_directory: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    env = {
        'PATH': os.environ.get('PATH', ''),
        'PYTHONPATH': str(project_root),
        'PYTHONDONTWRITEBYTECODE': '1',
        'IN_DOCKER': 'false',
        'BOT_TOKEN': '123456:production-placeholder',
        'TEST_BOT_TOKEN': '123456:development-placeholder',
        'ADMIN_ID': '1',
        'ADMIN_USERNAME': 'admin',
        'MAINTENANCE': 'false',
        'DB_URL': 'postgresql+asyncpg://test:test@127.0.0.1/test',
        'POSTGRES_DB': 'test',
        'POSTGRES_USER': 'test',
        'POSTGRES_PASSWORD': 'test',
        'COM_ID': '1',
        'PROXY_URL': '',
    }
    env.update(extra_env or {})
    result = subprocess.run(
        [sys.executable, '-W', 'error', '-c', script],
        cwd=working_directory,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result
