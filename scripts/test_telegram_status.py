"""Status command authorization, formatting and durable delivery; no live calls."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import telegram_status as status


SETTINGS = {'bot_id': '123', 'chat_id': '456'}


def update(identifier=2, text='/status'):
    return {'update_id': identifier, 'message': {'date': 1000, 'text': text,
        'from': {'id': 456, 'is_bot': False}, 'chat': {'id': 456, 'type': 'private'}}}


class StatusTests(unittest.TestCase):
    def test_commands_require_fresh_original_message_from_own_private_human(self):
        for text in ('/status', '!status', ' STATUS '):
            self.assertTrue(status.is_status_command(update(text=text), '456', 1000))
        invalid = [update(text='/restart'), {'edited_message': update()['message']}]
        for field, value in [('edit_date', 1000), ('forward_origin', {}),
                             ('forward_from', {}), ('forward_date', 1000),
                             ('sender_chat', {}), ('via_bot', {}), ('from', None), ('chat', None),
                             ('date', 1), ('date', 2000)]:
            item = update()
            item['message'][field] = value
            invalid.append(item)
        for field, value in [('from', {'id': 999, 'is_bot': False}),
                             ('from', {'id': 456, 'is_bot': True}),
                             ('chat', {'id': 456, 'type': 'group'}),
                             ('chat', {'id': 999, 'type': 'private'})]:
            item = update()
            item['message'][field] = value
            invalid.append(item)
        for item in invalid:
            self.assertFalse(status.is_status_command(item, '456', 1000))

    def test_ram_uses_available_memory_and_handles_missing_information(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'meminfo'
            path.write_text('MemTotal: 8388608 kB\nMemAvailable: 2097152 kB\n')
            self.assertIn('6.0 / 8.0 GiB used (75%)', status.memory_line(path))
            path.write_text('MemTotal: 0 kB\n')
            self.assertIn('unavailable', status.memory_line(path))

    def test_report_includes_services_ram_disk_backups_and_escapes_bounded_html(self):
        results = {'disk': {'level': 'ok', 'message': 'Disk: 20% used'},
                   'container:caddy': {'level': 'ok', 'message': 'running'},
                   'backup': {'level': 'critical', 'message': '<private & backup>'}}
        text = status.status_text(results, 1000, 'RAM: 2 / 8 GiB')
        for expected in ('2/3 checks healthy', 'RAM: 2 / 8 GiB', 'container:caddy',
                         'Disk: 20% used', '&lt;private &amp; backup&gt;'):
            self.assertIn(expected, text)
        large = {f'container:{i}': {'level': 'ok', 'message': '😀&' * 200} for i in range(100)}
        bounded = status.status_text(large, 1000, 'RAM')
        self.assertLessEqual(status.units(bounded), 3800)
        self.assertIn('omitted', bounded)

    def test_bootstrap_skips_history_then_fresh_command_freezes_cursor_before_send(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            observations = []
            def api(token, method, payload):
                if method == 'getWebhookInfo':
                    return {'url': ''}
                return [update(1 if payload['offset'] == -1 else 2)]
            def send(*args):
                saved = json.loads(path.read_text())
                self.assertEqual(saved['offset'], 3)
                self.assertEqual(saved['pending'][0]['status'], 'sending')
                observations.append(saved['pending'][0]['text'])
                return 'confirmed', 0
            with patch.object(status, 'request', side_effect=api), \
                 patch.object(status.time, 'time', return_value=1000), \
                 patch.object(status, 'collect', return_value={'disk': {'level': 'ok', 'message': '20%'}}) as collect, \
                 patch.object(status.telegram, 'send', side_effect=send), \
                 contextlib.redirect_stdout(io.StringIO()):
                status.poll({}, SETTINGS, 'fixture-token', path)
                collect.assert_not_called()
                status.poll({}, SETTINGS, 'fixture-token', path)
                status.poll({}, SETTINGS, 'fixture-token', path)
            collect.assert_called_once()
            self.assertEqual(len(observations), 1)
            self.assertEqual(json.loads(path.read_text())['pending'], [])

    def state(self, path):
        state = status.load_state(path, SETTINGS)
        state['offset'] = 1
        state['pending'] = [{'id': 1, 'text': 'Frozen report', 'status': 'queued',
                             'attempts': 0, 'retry_at': 0}]
        return state

    def test_ambiguous_and_interrupted_sends_are_never_replayed(self):
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'status.json'
                state = self.state(path)
                if interrupted:
                    state['pending'][0]['status'] = 'sending'
                status.save_state(path, state)
                with patch.object(status.telegram, 'send', return_value=('uncertain', 0)) as send:
                    state = status.load_state(path, SETTINGS)
                    status.deliver(state, path, 'fixture-token', 1000)
                    state = status.load_state(path, SETTINGS)
                    status.deliver(state, path, 'fixture-token', 1001)
                self.assertEqual(send.call_count, 0 if interrupted else 1)
                self.assertEqual(state['pending'][0]['status'], 'uncertain')

    def test_failed_claim_prevents_dispatch_and_confirmation_save_failure_is_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            state = self.state(path)
            with patch.object(status.telegram, 'send') as send:
                with self.assertRaises(OSError):
                    status.deliver(state, path, 'fixture-token', 1000,
                                   save=lambda *_: (_ for _ in ()).throw(OSError()))
                send.assert_not_called()
            state = self.state(path)
            saves = []
            def save(path, value):
                if saves:
                    raise OSError('disk failure after send')
                saves.append(True)
                status.save_state(path, value)
            with patch.object(status.telegram, 'send', return_value=('confirmed', 0)):
                with self.assertRaises(OSError):
                    status.deliver(state, path, 'fixture-token', 1000, save=save)
            self.assertEqual(status.load_state(path, SETTINGS)['pending'][0]['status'], 'uncertain')

    def test_only_explicit_rate_limits_retry_with_delay_and_three_attempt_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            state = self.state(path)
            with patch.object(status.telegram, 'send', return_value=('rate_limited', 5)) as send:
                for now in (1000, 1001, 1100, 1101, 1300, 1400):
                    status.deliver(state, path, 'fixture-token', now)
            self.assertEqual(send.call_count, 3)
            self.assertEqual(state['pending'][0]['status'], 'blocked')

    def test_unknown_versions_invalid_records_and_bot_changes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            base = self.state(path)
            for key, value in [('version', 2), ('bot_id', '999'), ('chat_id', '999'),
                               ('offset', -1), ('pending', [{}])]:
                state = copy.deepcopy(base)
                state[key] = value
                path.write_text(json.dumps(state))
                with self.assertRaises(ValueError):
                    status.load_state(path, SETTINGS)

    def test_menu_is_scoped_to_private_chat_and_verified(self):
        with patch.object(status, 'request', side_effect=[True, True, status.COMMANDS,
                                                        {'type': 'commands'}]) as api:
            status.configure_menu('fixture-token', '456')
        self.assertEqual(api.call_args_list[0].args[2]['scope'], {'type': 'chat', 'chat_id': '456'})
        self.assertEqual(api.call_args_list[1].args[2]['chat_id'], '456')

    def test_webhooks_fail_without_polling_or_dispatch_and_full_queue_can_drain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            state = self.state(path)
            status.save_state(path, state)
            with patch.object(status, 'request', return_value={'url': 'https://existing.invalid'}) as api, \
                 patch.object(status.telegram, 'send') as send:
                with self.assertRaises(ValueError):
                    status.poll({}, SETTINGS, 'fixture-token', path)
                api.assert_called_once()
                send.assert_not_called()
            state['pending'] = [dict(state['pending'][0], id=i) for i in range(status.MAX_REPLIES)]
            status.save_state(path, state)
            with patch.object(status, 'request') as api, \
                 patch.object(status.telegram, 'send', return_value=('confirmed', 0)), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(status.poll({}, SETTINGS, 'fixture-token', path), 1)
                api.assert_not_called()
            saved = json.loads(path.read_text())
            self.assertEqual(saved['offset'], 1)
            self.assertEqual(len(saved['pending']), status.MAX_REPLIES - 1)

    def test_token_bearing_transport_errors_are_sanitized_and_methods_restricted(self):
        with patch.object(status.urllib.request, 'build_opener', side_effect=OSError('SECRET-TOKEN')):
            with self.assertRaises(RuntimeError) as caught:
                status.request('SECRET-TOKEN', 'getUpdates', {})
        self.assertNotIn('SECRET', str(caught.exception))
        with self.assertRaises(ValueError):
            status.request('fixture-token', 'deleteWebhook', {})


if __name__ == '__main__':
    unittest.main()
