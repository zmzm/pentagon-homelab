import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import matrix_status


class StatusCommands(unittest.TestCase):
    def event(self, sender='@owner:server', body='!status', **content):
        return {'type': 'm.room.message', 'sender': sender, 'event_id': '$test',
                'content': {'msgtype': 'm.text', 'body': body, **content}}

    def test_authorization_commands_and_edits(self):
        for command in ('!status', ' status ', '/status', '!STATUS'):
            self.assertTrue(matrix_status.is_status_command(self.event(body=command), ['@owner:server']))
        for event in (self.event(sender='@stranger:server'), self.event(body='run shell'),
                      self.event(**{'m.relates_to': {'rel_type': 'm.replace'}})):
            self.assertFalse(matrix_status.is_status_command(event, ['@owner:server']))

    def test_initial_sync_ignores_history_then_command_gets_fresh_status(self):
        response = {'next_batch': 'next', 'rooms': {'join': {'!room': {
            'timeline': {'events': [self.event()]}}}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            config = {'notification': {'allowed_users': ['@owner:server']}}
            with patch.object(matrix_status, 'matrix_request', return_value=response), \
                 patch.object(matrix_status, 'collect', return_value={'disk': {'level': 'ok', 'message': '20% used'}}) as collect, \
                 patch('monitor.send_matrix') as send:
                matrix_status.poll(config, {'room_id': '!room'}, path)
                collect.assert_not_called()
                matrix_status.poll(config, {'room_id': '!room'}, path)
                collect.assert_called_once()
                self.assertIn('OK [disk] 20% used', send.call_args.args[1]['body'])
                self.assertEqual(json.loads(path.read_text())['pending'], [])


if __name__ == '__main__':
    unittest.main()
