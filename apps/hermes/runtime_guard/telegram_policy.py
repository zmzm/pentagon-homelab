"""Telegram authorization for this deployment, loaded before native startup.

The installed Hermes runner funnels message, callback and platform-event checks
through GatewayAuthorizationMixin. Keep this version-dependent integration small
and exercise it against the installed image before changing that image.
"""
import re


class TelegramPolicy:
    def __init__(self, allowed_users):
        entries = allowed_users.split(',')
        if not entries or any(re.fullmatch(r'[1-9][0-9]{0,15}', item.strip()) is None
                              for item in entries):
            raise ValueError('TELEGRAM_ALLOWED_USERS must contain positive numeric user IDs only')
        # Freeze the Compose-provided grant before native dotenv/profile loading.
        self.allowed_users = frozenset(item.strip() for item in entries)

    def allows(self, source):
        user_id = getattr(source, 'user_id', None)
        return (getattr(source, 'chat_type', None) == 'dm'
                and isinstance(user_id, str) and user_id in self.allowed_users
                and getattr(source, 'chat_id', None) == user_id
                and not getattr(source, 'is_bot', False))


def validate_home_channel(allowed_users, home_channel):
    policy = TelegramPolicy(allowed_users)
    if home_channel and home_channel not in policy.allowed_users:
        raise ValueError('Telegram home channel must be an allowed private user ID')


def install(allowed_users):
    policy = TelegramPolicy(allowed_users)
    from gateway.authz_mixin import GatewayAuthorizationMixin

    original_authorize = GatewayAuthorizationMixin._is_user_authorized
    original_dm_behavior = GatewayAuthorizationMixin._get_unauthorized_dm_behavior

    def authorize(self, source, *, allow_adapter_delegation=True):
        if getattr(getattr(source, 'platform', None), 'value', None) == 'telegram':
            # No pairing/global/chat/role grants can broaden this policy.
            return policy.allows(source)
        return original_authorize(self, source, allow_adapter_delegation=allow_adapter_delegation)

    def dm_behavior(self, platform, *, profile=None):
        if getattr(platform, 'value', None) == 'telegram':
            return 'ignore'
        return original_dm_behavior(self, platform, profile=profile)

    GatewayAuthorizationMixin._is_user_authorized = authorize
    GatewayAuthorizationMixin._get_unauthorized_dm_behavior = dm_behavior
