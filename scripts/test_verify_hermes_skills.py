"""Regression checks for validation of actual Hermes deferred-call shapes."""
import copy
import json
import unittest

from verify_hermes_skills import check_behavior


def message(calls):
    return {'role': 'assistant', 'content': '', 'tool_calls': json.dumps([
        {'function': {'name': c['name'], 'arguments': json.dumps(c['arguments'])}}
        for c in calls])}


def fixture(deferred=True):
    reads = [
        {'name': 'mcp__personal__homelab_inspect_service', 'arguments': {'service': 'vaultwarden'}},
        {'name': 'mcp__personal__homelab_get_logs', 'arguments': {'service': 'vaultwarden', 'lines': 100}},
        {'name': 'mcp__personal__knowledge_search', 'arguments': {'project': 'homelab'}},
    ]
    calls = [{'name': 'skill_view', 'arguments': {'name': 'homelab-service-diagnosis'}}]
    if deferred:
        calls += [{'name': 'tool_describe', 'arguments': {'names': [r['name'] for r in reads]}},
                  {'name': 'tool_call', 'arguments': {'calls': reads}}]
    else:
        calls += reads
    return {'sessions': [{'id': 'fixture', 'source': 'oneshot', 'model': 'fixture', 'messages': [
        {'role': 'user', 'content': 'diagnose', 'tool_calls': None}, message(calls),
        {'role': 'assistant', 'content': 'Fixture answer, not model acceptance.', 'tool_calls': None},
    ]}], 'http_calls': []}


class DeferredCallsTest(unittest.TestCase):
    def test_native_bridge_and_direct_calls_have_same_diagnostic_inventory(self):
        direct = check_behavior(fixture(False), {'diagnosis': 'diagnose'})[0]
        deferred = check_behavior(fixture(), {'diagnosis': 'diagnose'})[0]
        self.assertEqual(direct['calls'], deferred['calls'])

    def test_write_inside_read_batch_is_rejected(self):
        observation = fixture()
        calls = json.loads(observation['sessions'][0]['messages'][1]['tool_calls'])
        batch = json.loads(calls[-1]['function']['arguments'])
        batch['calls'].append({'name': 'mcp__personal__homelab_restart_service',
                               'arguments': {'service': 'vaultwarden'}})
        calls[-1]['function']['arguments'] = json.dumps(batch)
        observation['sessions'][0]['messages'][1]['tool_calls'] = json.dumps(calls)
        with self.assertRaisesRegex(RuntimeError, 'unexpected tool call'):
            check_behavior(observation, {'diagnosis': 'diagnose'})

    def test_unanswered_clarification_does_not_authorize_inspection(self):
        observation = fixture()
        messages = observation['sessions'][0]['messages']
        messages.insert(1, message([{'name': 'clarify', 'arguments': {'questions': []}}]))
        messages.insert(2, {'role': 'tool', 'content': json.dumps({'outcome': 'undelivered'}),
                            'tool_calls': None})
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous target was inspected'):
            check_behavior(observation, {'ambiguous': 'diagnose'})

    def test_blocked_http_attempt_fails_acceptance(self):
        observation = copy.deepcopy(fixture())
        observation['http_calls'].append({'allowed': False, 'path': '/approvals'})
        with self.assertRaisesRegex(RuntimeError, 'non-diagnostic HTTP call was attempted'):
            check_behavior(observation, {'diagnosis': 'diagnose'})

    def test_unanswered_clarification_stops_with_a_question_and_no_mcp_calls(self):
        observation = fixture()
        messages = observation['sessions'][0]['messages']
        messages[1] = message([
            {'name': 'skill_view', 'arguments': {'name': 'homelab-service-diagnosis'}},
            {'name': 'clarify', 'arguments': {'questions': []}},
        ])
        messages.insert(2, {'role': 'tool', 'tool_calls': None, 'content': json.dumps({
            'outcome': 'undelivered', 'responses': [{'status': 'unanswered', 'user_response': None}],
            'notice': 'Make a reasonable assumption and continue.',
        })})
        messages[-1]['content'] = 'Which Matrix target should I diagnose: the homeserver or its database?'
        case = check_behavior(observation, {'ambiguous': 'diagnose'})[0]
        self.assertEqual([c['name'] for c in case['calls']], ['skill_view', 'clarify'])

    def test_ambiguous_stop_without_a_question_is_incomplete(self):
        observation = fixture()
        observation['sessions'][0]['messages'][1] = message([
            {'name': 'skill_view', 'arguments': {'name': 'homelab-service-diagnosis'}},
        ])
        with self.assertRaisesRegex(RuntimeError, 'did not end with a clarification question'):
            check_behavior(observation, {'ambiguous': 'diagnose'})


if __name__ == '__main__':
    unittest.main()
