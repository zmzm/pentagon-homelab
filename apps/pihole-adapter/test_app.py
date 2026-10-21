import contextlib
import io
import unittest
from unittest.mock import Mock, patch

import app as adapter


class SessionPrivacy(unittest.TestCase):
    def setUp(self):
        adapter._cached_sid = None
        adapter._sid_expires_at = 0
        adapter._summary_cache = None
        adapter._summary_cache_until = 0

    def tearDown(self):
        adapter._cached_sid = None
        adapter._sid_expires_at = 0
        adapter._summary_cache = None
        adapter._summary_cache_until = 0

    def test_session_lifecycle_keeps_tokens_out_of_logs(self):
        token = 'private-session-token-fixture'
        auth = Mock()
        auth.json.return_value = {'session': {'sid': token, 'validity': 300}}
        summary = Mock(status_code=200)
        summary.json.return_value = {'queries': {'total': 12, 'blocked': 3}}
        output = io.StringIO()
        with patch.object(adapter.http, 'post', return_value=auth) as login, \
                patch.object(adapter.http, 'get', return_value=summary) as get, \
                patch.object(adapter.http, 'delete', return_value=Mock(status_code=204)) as logout, \
                contextlib.redirect_stdout(output):
            self.assertEqual(adapter.get_sid(), token)
            self.assertEqual(adapter.get_sid(), token)
            self.assertEqual(adapter.fetch_summary()['queries_total'], 12)
            adapter.clear_cached_sid()
        login.assert_called_once()
        self.assertEqual(get.call_args.kwargs['headers']['X-FTL-SID'], token)
        self.assertEqual(logout.call_args.kwargs['headers']['X-FTL-SID'], token)
        self.assertNotIn(token, output.getvalue())

    def test_invalid_auth_response_does_not_expose_response_body(self):
        secret = 'private-auth-response-fixture'
        auth = Mock()
        auth.json.return_value = {'session': {}, 'sensitive': secret}
        with patch.object(adapter.http, 'post', return_value=auth):
            with self.assertRaises(RuntimeError) as error:
                adapter.login()
        self.assertNotIn(secret, str(error.exception))

    def test_summary_errors_do_not_expose_exception_details(self):
        secret = 'private-exception-fixture'
        output = io.StringIO()
        with patch.object(adapter.http, 'post', side_effect=RuntimeError(secret)), \
                contextlib.redirect_stdout(output):
            response = adapter.app.test_client().get('/pihole-summary')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json, {'status': 'error', 'error': 'RuntimeError'})
        self.assertNotIn(secret, response.get_data(as_text=True) + output.getvalue())


if __name__ == '__main__':
    unittest.main()
