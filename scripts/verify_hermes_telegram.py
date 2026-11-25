"""Run in an isolated installed-image home, never against production credentials.

Exercises the native Telegram adapter without connecting it or invoking a model.
The existing verify_hermes_skills.py offline harness supplies mounts and fixtures.
"""
import asyncio
import os
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from gateway.authz_mixin import GatewayAuthorizationMixin
from gateway.config import Platform, load_gateway_config
from gateway.slash_access import policy_for_source
from gateway.session import SessionSource
from plugins.platforms.telegram.adapter import TelegramAdapter, _redact_telegram_error_text
from telegram import Chat, Message, Update, User


class TelegramConfigurationTests(unittest.TestCase):
    def setUp(self):
        # Process-local fixtures; no bot connection and no production secrets.
        self.env = patch.dict(os.environ, {
            'TELEGRAM_BOT_TOKEN': '123456:offline-fixture',
            'TELEGRAM_ALLOWED_USERS': '123456',
            'TELEGRAM_ALLOW_ALL_USERS': 'false',
            'TELEGRAM_ALLOW_BOTS': 'none',
            'TELEGRAM_GROUP_ALLOWED_USERS': '',
            'TELEGRAM_GROUP_ALLOWED_CHATS': '',
            'TELEGRAM_GUEST_MODE': 'false',
            'TELEGRAM_OBSERVE_UNMENTIONED_GROUP_MESSAGES': 'false',
            'TELEGRAM_WEBHOOK_URL': '',
            'GATEWAY_ALLOWED_USERS': '',
            'GATEWAY_ALLOW_ALL_USERS': 'false',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.config = load_gateway_config()
        self.native = self.config.platforms[Platform.TELEGRAM]
        self.adapter = TelegramAdapter(self.native)
        self.runner = GatewayAuthorizationMixin()
        self.runner.config = self.config
        self.runner.adapters = {Platform.TELEGRAM: self.adapter}
        self.adapter.set_authorization_check(lambda user_id, chat_type, chat_id, **kwargs:
            self.runner._is_user_authorized(SessionSource(
                platform=Platform.TELEGRAM, chat_id=chat_id or user_id,
                chat_type=chat_type or 'dm', user_id=user_id, **kwargs)))

    def message(self, user_id=123456, chat_type='private', sender_chat=False):
        chat_id = user_id if chat_type == 'private' else -100123456
        return Message(
            message_id=1, date=datetime.now(timezone.utc),
            chat=Chat(chat_id, chat_type, is_forum=chat_type == 'supergroup'),
            text='hello @fixture_bot',
            message_thread_id=2 if chat_type == 'supergroup' else None,
            is_topic_message=chat_type == 'supergroup',
            from_user=None if sender_chat else User(user_id, 'Fixture', False),
            sender_chat=Chat(chat_id, chat_type) if sender_chat else None,
        )

    def test_effective_native_configuration(self):
        self.assertTrue(self.native.enabled)
        self.assertEqual(self.native.token, os.environ['TELEGRAM_BOT_TOKEN'])
        self.assertEqual(self.native.extra['group_allow_from'], [])
        self.assertEqual(self.runner._get_unauthorized_dm_behavior(Platform.TELEGRAM), 'ignore')
        self.assertFalse(self.adapter._telegram_guest_mode())
        self.assertFalse(self.adapter._telegram_observe_unmentioned_group_messages())
        self.assertFalse(os.environ['TELEGRAM_WEBHOOK_URL'])

    def test_authorized_dm_and_unknown_sender(self):
        self.assertTrue(self.adapter._is_user_authorized_from_message(self.message()))
        self.assertFalse(self.adapter._is_user_authorized_from_message(self.message(654321)))
        # A forged display name never substitutes for the numeric sender ID.
        self.assertFalse(self.adapter._is_callback_user_authorized('654321', user_name='123456'))

    def test_group_channel_and_anonymous_senders(self):
        for kind in ('group', 'supergroup', 'channel'):
            for sender_chat in (False, True):
                with self.subTest(kind=kind, sender_chat=sender_chat):
                    self.assertFalse(self.adapter._is_user_authorized_from_message(
                        self.message(chat_type=kind, sender_chat=sender_chat)))

    def test_unauthorized_text_stops_before_event_construction(self):
        self.adapter._build_triggered_event = AsyncMock()
        self.adapter._enqueue_text_event = Mock()
        asyncio.run(self.adapter._handle_text_message(
            Update(1, message=self.message(654321)), None))
        self.adapter._build_triggered_event.assert_not_called()
        self.adapter._enqueue_text_event.assert_not_called()

    def test_denied_intake_never_builds_dispatches_or_downloads(self):
        # Exercise real intake handlers, not just their authorization predicate.
        # Commands need a bot-addressing decision first; it is not an auth gate.
        self.adapter._should_process_message = Mock(return_value=True)
        self.adapter._build_triggered_event = AsyncMock()
        self.adapter._build_message_event = Mock()
        self.adapter._enqueue_text_event = Mock()
        self.adapter.handle_message = AsyncMock()
        self.adapter._cache_observed_media = AsyncMock()
        for kind, user_id in (('private', 654321), ('group', 123456),
                              ('supergroup', 123456), ('channel', 123456)):
            for handler in ('_handle_text_message', '_handle_command',
                            '_handle_location_message', '_handle_media_message'):
                with self.subTest(kind=kind, handler=handler):
                    message = self.message(user_id, kind)
                    update = Update(1, channel_post=message) if kind == 'channel' else Update(1, message=message)
                    asyncio.run(getattr(self.adapter, handler)(update, None))
        self.adapter._build_triggered_event.assert_not_called()
        self.adapter._build_message_event.assert_not_called()
        self.adapter._enqueue_text_event.assert_not_called()
        self.adapter.handle_message.assert_not_called()
        self.adapter._cache_observed_media.assert_not_called()

    def test_unknown_inline_query_does_not_read_catalog(self):
        query = SimpleNamespace(from_user=User(654321, 'Fixture', False), answer=AsyncMock())
        with patch('plugins.platforms.telegram.inline_picker.build_inline_results') as catalog:
            asyncio.run(self.adapter._handle_inline_query(SimpleNamespace(inline_query=query), None))
        catalog.assert_not_called()
        self.assertEqual(query.answer.await_args.args, ([],))

    def test_unknown_callbacks_do_not_dispatch_or_consume_pending_state(self):
        self.adapter._handle_model_picker_callback = AsyncMock()
        self.adapter._handle_choice_picker_callback = AsyncMock()
        self.adapter._approval_state = {7: 'fixture-session'}
        self.adapter._slash_confirm_state = {'fixture': 'fixture-session'}
        self.adapter._clarify_state = {'fixture': 'fixture-session'}
        for data in ('mp:fixture', 'cp:fixture', 'ea:once:7',
                     'sc:once:fixture', 'cl:fixture:0', 'update_prompt:y'):
            with self.subTest(data=data):
                query = SimpleNamespace(data=data, from_user=User(654321, 'Fixture', False),
                                        message=self.message(), answer=AsyncMock())
                asyncio.run(self.adapter._handle_callback_query(SimpleNamespace(callback_query=query), None))
                query.answer.assert_awaited_once()
        self.adapter._handle_model_picker_callback.assert_not_called()
        self.adapter._handle_choice_picker_callback.assert_not_called()
        self.assertEqual(self.adapter._approval_state, {7: 'fixture-session'})
        self.assertEqual(self.adapter._slash_confirm_state, {'fixture': 'fixture-session'})
        self.assertEqual(self.adapter._clarify_state, {'fixture': 'fixture-session'})

    def test_unknown_dm_ignore_does_not_create_pairing_request(self):
        self.runner.pairing_store = Mock()
        self.runner.pairing_store.is_approved.return_value = False
        self.adapter.gateway_runner = self.runner
        self.adapter._build_triggered_event = AsyncMock()
        asyncio.run(self.adapter._handle_text_message(Update(1, message=self.message(654321)), None))
        self.adapter._build_triggered_event.assert_not_called()
        # Approval lookup is permitted; no native pairing store mutation occurs.
        self.assertTrue(self.runner.pairing_store.mock_calls)
        self.assertTrue(all(call[0] == 'is_approved' for call in self.runner.pairing_store.mock_calls))

    def test_blocked_intake_logs_exclude_message_and_credentials(self):
        message = Message(message_id=1, date=datetime.now(timezone.utc),
                          chat=Chat(654321, 'private'), from_user=User(654321, 'Fixture', False),
                          text='PRIVATE-FIXTURE-BODY ' + os.environ['TELEGRAM_BOT_TOKEN'])
        with self.assertLogs('plugins.platforms.telegram.adapter', level='WARNING') as logs:
            asyncio.run(self.adapter._handle_text_message(Update(1, message=message), None))
        for secret in ('PRIVATE-FIXTURE-BODY', os.environ['TELEGRAM_BOT_TOKEN']):
            self.assertNotIn(secret, '\n'.join(logs.output))

    def test_transport_error_redacts_fixture_bot_token(self):
        token = '123456789:AAExampleTokenValueForOfflineFixture123'
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': token}):
            safe = _redact_telegram_error_text(RuntimeError('https://api.telegram.org/bot' + token + '/getUpdates'))
        self.assertNotIn(token, safe)

    def test_known_gap_group_callback_bypasses_message_sender_gate(self):
        # Characterize a deployment blocker, not a successful group-denial check.
        self.assertFalse(self.adapter._is_user_authorized_from_message(self.message(chat_type='group')))
        self.assertTrue(self.adapter._is_callback_user_authorized(
            '123456', chat_id='-100123456', chat_type='group'))

    def test_known_gap_wildcard_allowlist_overrides_closed_access_flags(self):
        with patch.dict(os.environ, {'TELEGRAM_ALLOWED_USERS': '*'}):
            self.assertTrue(self.adapter._is_user_authorized_from_message(self.message(654321)))

    def test_native_slash_commands_do_not_restore_admin_tools(self):
        source = SessionSource(platform=Platform.TELEGRAM, chat_id='123456',
                               chat_type='dm', user_id='123456')
        policy = policy_for_source(self.config, source)
        self.assertTrue(policy.enabled)
        for command in ('help', 'whoami', 'new', 'reset', 'stop', 'status'):
            self.assertTrue(policy.can_run(source.user_id, command), command)
        for command in ('cron', 'schedule', 'terminal', 'shell', 'update', 'reload',
                        'config', 'tools', 'model', 'approve', 'skills'):
            self.assertFalse(policy.can_run(source.user_id, command), command)

    def test_retained_pairing_is_an_additional_grant(self):
        # Records are a native authorization UNION, even with an explicit allowlist.
        # Keep this limitation visible: deployment must check both pairing layouts.
        self.runner.pairing_store = Mock()
        self.runner.pairing_store.is_approved.return_value = True
        source = SessionSource(platform=Platform.TELEGRAM, chat_id='654321',
                               chat_type='dm', user_id='654321')
        self.assertTrue(self.runner._is_user_authorized(source))
        self.assertTrue(self.adapter._is_user_authorized_from_message(self.message(654321)))
        self.assertTrue(self.adapter._is_callback_user_authorized('654321'))


if __name__ == '__main__':
    print('NOTICE: known-gap tests characterize wildcard, retained-pairing and group-callback grants; '
          'passing tests do not clear deployment blockers.', flush=True)
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
