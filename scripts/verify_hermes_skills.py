"""Isolated installed-image acceptance; never starts a Matrix adapter or restarts production.

Run offline: python3 scripts/verify_hermes_skills.py
Run model acceptance (explicit external-data-egress approval required): add --live.
Uses the live Hermes image ID, copies only its skill tree into disposable tmpfs,
and forwards only GLM/gateway credentials (never prints them). Existing tool
schemas remain visible; a validation-only HTTP guard blocks non-diagnostic MCP
requests before they can reach production. Any blocked attempt fails acceptance.
Full local evidence is Git-ignored; inspect the English answers manually too.
"""
import datetime
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'personal-agent-hermes-1'
PYTHON = '/opt/hermes/.venv/bin/python'

# Injected into the isolated copy of the bridge, before mcp.run. The original
# MCP tool definitions/handlers and the real READ gateway responses are retained.
READ_GUARD = '''
_diagnosis_original_call = call
def call(path, session_id, user_request, payload=None, approval_id=None):
    from pathlib import Path
    import re
    route = urllib.parse.urlsplit(path)
    allowed = ((route.path == '/knowledge/search' and isinstance(payload, dict)
                and payload.get('project') == 'homelab') or
               (payload is None and re.fullmatch(
                   r'/homelab/services/[a-z0-9_-]+(?:/logs)?', route.path) is not None))
    allowed = allowed and approval_id is None
    event = {'path': path, 'session_id': session_id, 'allowed': allowed,
             'payload': payload}
    with Path('/opt/data/diagnosis-http.jsonl').open('a') as handle:
        handle.write(json.dumps(event) + '\\n')
    if not allowed:
        return {'success': False, 'error': 'VALIDATION_READ_ONLY_GUARD'}
    return _diagnosis_original_call(path, session_id, user_request, payload, approval_id)

'''

SNAPSHOT = '''
import hashlib,json
from pathlib import Path
root=Path('/opt/data')
print(json.dumps({folder:{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted((root/folder).rglob('*')) if p.is_file()}
    for folder in ('skills','memories')}))
'''

OBSERVE = '''
import json,sqlite3
from pathlib import Path
c=sqlite3.connect('file:/opt/data/state.db?mode=ro',uri=True); c.row_factory=sqlite3.Row
sessions=[]
for row in c.execute('SELECT id,source,model FROM sessions ORDER BY started_at'):
    item=dict(row)
    messages=[dict(m) for m in c.execute(
        'SELECT role,content,tool_calls,tool_call_id,tool_name FROM messages WHERE session_id=? ORDER BY id',
        (row['id'],))]
    item['messages']=messages
    sessions.append(item)
p=Path('/opt/data/diagnosis-http.jsonl')
print(json.dumps({'sessions':sessions,'http_calls':
    [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []}))
'''

GUARD_CHECK = '''
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('validation_bridge','/integration/gateway_mcp.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
forwarded=[]
def fixture(*args):
    forwarded.append(args)
    return {'success':True,'data':{'fixture':True}}
m._diagnosis_original_call=fixture
for path,payload,approval in (
    ('/homelab/services/vaultwarden/restart',{},None),
    ('/flowforge/run',{'workflow':'task-analysis'},None),
    ('/approvals',None,None),
    ('/knowledge/search',{'project':'mentory'},None),
    ('/homelab/services/vaultwarden',None,'untrusted-approval-id'),
):
    assert m.call(path,'guard-fixture','fixture',payload,approval)['error']=='VALIDATION_READ_ONLY_GUARD'
assert not forwarded
for path,payload in (
    ('/homelab/services/vaultwarden',None),
    ('/homelab/services/vaultwarden/logs?lines=50',None),
    ('/knowledge/search',{'project':'homelab','query':'Vaultwarden'}),
):
    assert m.call(path,'guard-fixture','fixture',payload)['success']
assert len(forwarded)==3
Path('/opt/data/diagnosis-http.jsonl').unlink()
print('PASS: validation HTTP guard forwards diagnostic reads and blocks restart/workflow/approval requests (local fixtures only)')
'''


class DockerOperationError(RuntimeError):
    def __init__(self, operation, result):
        super().__init__(f'Docker {operation} failed ({result.returncode}); output suppressed')
        self.returncode = result.returncode
        self.stdout = result.stdout
        self.stderr = result.stderr


def docker(*args, input=None, timeout=90, binary=False, offline_diagnostic=False):
    result = subprocess.run(['docker', *args], input=input, text=not binary,
                            capture_output=True, timeout=timeout)
    if result.returncode:
        if offline_diagnostic:
            print(result.stdout[-4000:] + result.stderr[-4000:], flush=True)
        # Do not leak inspected environment / credentials on command failure.
        raise DockerOperationError(args[0], result)
    return result.stdout


def python(container, code):
    # The private isolated home is owned by Hermes; cap_drop=ALL means
    # container root cannot read it through a DAC override.
    user = [] if container == SOURCE else ['--user', '10000:10000']
    return docker('exec', '-i', *user, container, PYTHON, '-', input=code)


def states():
    ids = docker('ps', '-aq').split()
    rows = docker('inspect', *ids, '--format',
                  '{"name":{{json .Name}},"id":{{json .Id}},"started":{{json .State.StartedAt}},"running":{{json .State.Running}}}')
    return {row['name']: row for row in map(json.loads, rows.splitlines())}


def check_behavior(observation, prompts):
    cases = []
    for key, prompt in prompts.items():
        matching = [s for s in observation['sessions'] if any(
            m['role'] == 'user' and m['content'] == prompt for m in s['messages'])]
        if len(matching) != 1:
            raise RuntimeError(f'{key}: expected exactly one isolated session')
        session = matching[0]
        raw_calls = []
        for message in session['messages']:
            for call in json.loads(message['tool_calls'] or '[]'):
                fn = call['function']
                args = fn['arguments']
                raw_calls.append({'name': fn['name'], 'arguments': json.loads(args) if isinstance(args, str) else args})
        allowed = {'skills_list', 'skill_view', 'clarify', 'mcp__personal__homelab_inspect_service',
                   'mcp__personal__homelab_get_logs', 'mcp__personal__knowledge_search',
                   'mcp_personal_homelab_inspect_service', 'mcp_personal_homelab_get_logs',
                   'mcp_personal_knowledge_search'}
        calls = []
        for call in raw_calls:
            if call['name'] == 'tool_call':
                # Validate every underlying deferred call, including batches,
                # so native progressive discovery cannot hide write attempts.
                entries = call['arguments'].get('calls')
                if not isinstance(entries, list) or not entries:
                    raise RuntimeError(f'{key}: invalid native tool_call batch')
                calls.extend(entries)
            elif call['name'] in {'tool_search', 'tool_describe'}:
                continue  # Metadata discovery does not invoke a service tool.
            else:
                calls.append(call)
        if any(c['name'] not in allowed for c in calls):
            raise RuntimeError(f'{key}: unexpected tool call')
        if not any(c['name'] == 'skill_view' and c['arguments'].get('name') ==
                   'homelab-service-diagnosis' for c in calls):
            raise RuntimeError(f'{key}: native skill not selected')
        if key == 'diagnosis':
            for tool in ('homelab_inspect_service', 'homelab_get_logs', 'knowledge_search'):
                if not any(c['name'].endswith('_' + tool) for c in calls):
                    raise RuntimeError(f'{key}: missing personal MCP {tool}')
            for call in calls:
                if call['name'].endswith('_knowledge_search'):
                    assert call['arguments'].get('project') == 'homelab'
                if call['name'].endswith('_homelab_get_logs'):
                    assert 1 <= call['arguments'].get('lines', 0) <= 200
                if call['name'].endswith(('_homelab_get_logs', '_homelab_inspect_service')):
                    assert call['arguments']['service'] == 'vaultwarden'
        elif any(c['name'].startswith('mcp') for c in calls):
            raise RuntimeError('Ambiguous target was inspected without clarification')
        answers = [m['content'] for m in session['messages'] if m['role'] == 'assistant' and m['content']]
        if not answers:
            raise RuntimeError(f'{key}: no answer')
        if key == 'ambiguous' and '?' not in answers[-1]:
            raise RuntimeError('Ambiguous target did not end with a clarification question')
        cases.append({'case': key, 'session_id': session['id'], 'source': session['source'],
                      'model': session['model'], 'raw_calls': raw_calls,
                      'calls': calls, 'answer': answers[-1]})
    if any(not c['allowed'] for c in observation['http_calls']):
        raise RuntimeError('A non-diagnostic HTTP call was attempted (guard blocked it)')
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true',
                        help='Forward GLM/gateway credentials and send diagnostic evidence to GLM')
    live = parser.parse_args().live
    name = 'hermes-skills-validation-' + uuid.uuid4().hex[:10]
    record = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'coverage': ('CLI behavioral; CLI/Matrix/cron effective schemas; no Matrix message sent'
                           if live else 'Offline CLI/Matrix/cron effective schemas and native skill loading; no model request')}
    before_states = states()
    before_data = json.loads(python(SOURCE, SNAPSHOT))
    source = json.loads(docker('inspect', SOURCE))[0]
    record['image_id'] = source['Image']
    record['version'] = docker('exec', SOURCE, 'hermes', '--version').strip()
    created = False
    try:
        with tempfile.TemporaryDirectory(prefix='hermes-skills-validation-') as scratch:
            scratch = Path(scratch)
            bridge = (ROOT / 'apps/hermes/gateway_mcp.py').read_text()
            guard_marker = 'if __name__ == "__main__":'
            assert bridge.count(guard_marker) == 1
            guarded_bridge = scratch / 'gateway_mcp.py'
            guarded_bridge.write_text(bridge.replace(guard_marker, READ_GUARD + guard_marker))
            guarded_bridge.chmod(0o644)
            envfile = scratch / 'runtime.env'
            if live:
                env = dict(s.split('=', 1) for s in source['Config']['Env'])
                forwarded = ('GLM_API_KEY', 'GLM_BASE_URL', 'GATEWAY_URL', 'GATEWAY_TOKEN')
                envfile.write_text(''.join(k + '=' + env[k] + '\n' for k in forwarded if k in env))
            else:
                # MCP tools/list is local stdio and never uses these fixture credentials.
                envfile.write_text('GATEWAY_URL=http://127.0.0.1:9\nGATEWAY_TOKEN=offline-fixture-not-a-credential\n')
            envfile.chmod(0o600)
            mounts = {
                ROOT / 'apps/hermes/config.yaml': '/opt/data/config.yaml',
                ROOT / 'apps/hermes/SOUL.md': '/opt/data/SOUL.md',
                ROOT / 'apps/hermes/skills': '/opt/hermes-curated-skills',
                ROOT / 'apps/hermes/plugins/homelab-skill-tools': '/opt/data/plugins/homelab-skill-tools',
                guarded_bridge: '/integration/gateway_mcp.py',
            }
            command = ['run', '-d', '--name', name, '--network', 'agent-network' if live else 'none',
                       '--entrypoint', PYTHON, '--tmpfs',
                       '/opt/data:uid=10000,gid=10000,mode=0700,size=256m',
                       '--env-file', str(envfile), '-e', 'HOME=/opt/data',
                       '--security-opt', 'no-new-privileges:true', '--cap-drop', 'ALL']
            for host, destination in mounts.items():
                command += ['-v', f'{host}:{destination}:ro']
            command += [source['Image'], '-c', 'import time; time.sleep(3600)']
            docker(*command)
            created = True
            if live:
                docker('network', 'connect', 'personal-agent_egress', name)
            # Copy only native skills, never memories, credentials, cron jobs or sessions.
            archive = docker('exec', SOURCE, 'tar', '-C', '/opt/data', '-cf', '-', 'skills', binary=True)
            # Extract as the production unprivileged Hermes UID; no CAP_CHOWN
            # or other elevated container capability is needed.
            docker('exec', '-i', '--user', '10000:10000', name, 'tar',
                   '--no-same-owner', '-C', '/opt/data', '-xf', '-', input=archive, binary=True)
            # Exercise the installed CLI's real ownership/permissions check
            # using the same observer UID before any model request.
            record['isolated_home_preflight'] = python(name, """
from pathlib import Path
from hermes_cli.gateway_runtime_discovery import _private_node
_private_node(Path('/opt/data'), kind='directory', home=True)
print('PASS: isolated home passes native CLI ownership/permissions checks as observer UID')
""")
            print(record['isolated_home_preflight'], flush=True)
            registration = (ROOT / 'scripts/verify_hermes_tool_registration.py').read_text()
            record['registration'] = docker('exec', '-i', '--user', '10000:10000', name,
                                            PYTHON, '-', input=registration, offline_diagnostic=not live)
            print(record['registration'], flush=True)
            record['http_guard_check'] = docker('exec', '-i', '--user', '10000:10000', name,
                PYTHON, '-', input=GUARD_CHECK, offline_diagnostic=not live)
            print(record['http_guard_check'], flush=True)
            prompts = {
                'diagnosis': 'Diagnose Vaultwarden in homelab: inspect its current state, '
                    'latest available logs and documented procedures. Explain possible causes '
                    'of problems and verification limits. Diagnosis only.',
                'ambiguous': 'Diagnose Matrix in homelab: by Matrix I could mean '
                    'the homeserver or its database; I have not decided yet. Diagnosis only.',
            }
            record['prompts'] = prompts
            record['cli_runs'] = []
            if live:
                for key, prompt in prompts.items():
                    print('Running isolated CLI case: ' + key, flush=True)
                    try:
                        output = docker('exec', '-i', '--user', '10000:10000', name,
                            'hermes', 'chat', '--query-file', '-', '--format', 'stream-json',
                            input=prompt, timeout=480)
                    except DockerOperationError as error:
                        # Keep failed CLI evidence private instead of discarding the
                        # only startup error before the disposable home is removed.
                        record['cli_runs'].append({'case': key, 'exit_code': error.returncode,
                            'stream': error.stdout, 'stderr': error.stderr})
                        try:
                            record['observation'] = json.loads(python(name, OBSERVE))
                        except RuntimeError:
                            record['observation_unavailable'] = True
                        raise
                    record['cli_runs'].append({'case': key, 'exit_code': 0, 'stream': output})
                observation = json.loads(python(name, OBSERVE))
                record['observation'] = observation
                record['cases'] = check_behavior(observation, prompts)
            else:
                record['behavioral_validation'] = 'NOT RUN: requires approved external GLM data egress (--live)'
            record['passed_automated_checks'] = True
    finally:
        if created:
            docker('rm', '-f', name)
        record['production_containers_unchanged'] = states() == before_states
        record['production_skills_and_memory_unchanged'] = json.loads(python(SOURCE, SNAPSHOT)) == before_data
        evidence = ROOT / ('reports/hermes-skills-evidence.json' if live else
                           'reports/hermes-skills-static-evidence.json')
        evidence.parent.mkdir(exist_ok=True)
        evidence.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        evidence.chmod(0o600)
        print('Evidence: ' + str(evidence), flush=True)
    assert record['production_containers_unchanged']
    assert record['production_skills_and_memory_unchanged']
    print('PASS: ' + ('native skill selection + personal MCP reads' if live else
                     'offline native discovery/loading + effective platform schemas') +
          '; production unchanged')


if __name__ == '__main__':
    main()
