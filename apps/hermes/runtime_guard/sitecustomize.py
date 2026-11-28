"""Apply the deployment's Telegram policy in every native Python gateway process.

PYTHONPATH selects this read-only directory for CLI and supervisor subprocesses.
Fail closed: Python normally logs Exception from sitecustomize and continues;
SystemExit instead stops startup. Never print configured IDs or exception text.
"""
import os

if os.environ.get('TELEGRAM_BOT_TOKEN'):
    try:
        from telegram_policy import install, validate_home_channel
        validate_home_channel(os.environ.get('TELEGRAM_ALLOWED_USERS', ''),
                              os.environ.get('TELEGRAM_HOME_CHANNEL', ''))
        install(os.environ.get('TELEGRAM_ALLOWED_USERS', ''))
    except Exception:
        raise SystemExit('Hermes Telegram policy initialization failed; check numeric user IDs and runtime compatibility') from None
