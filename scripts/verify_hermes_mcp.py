"""Run inside Hermes: real MCP handshake, nine tools, policy discovery and read-only inspection."""
import asyncio
import json
import sys


async def main():
    process = await asyncio.create_subprocess_exec(
        sys.executable, '/integration/gateway_mcp.py',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    async def send(message):
        process.stdin.write((json.dumps({'jsonrpc': '2.0', **message}) + '\n').encode())
        await process.stdin.drain()

    async def receive(request_id):
        while True:
            raw = await asyncio.wait_for(process.stdout.readline(), 40)
            if not raw:
                raise RuntimeError('MCP server closed before replying')
            message = json.loads(raw)
            if message.get('id') == request_id:
                if 'error' in message:
                    raise RuntimeError('MCP returned a protocol error')
                return message['result']

    try:
        await send({'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'homelab-read-only-smoke', 'version': '1.0'},
        }})
        await receive(1)
        await send({'method': 'notifications/initialized'})
        await send({'id': 2, 'method': 'tools/list', 'params': {}})
        tools = (await receive(2))['tools']
        expected = {'knowledge_search', 'flowforge_list_workflows', 'flowforge_list_tasks', 'flowforge_get_run', 'flowforge_run',
                    'homelab_list_services', 'homelab_inspect_service', 'homelab_get_logs', 'homelab_restart_service'}
        if {tool['name'] for tool in tools} != expected:
            raise RuntimeError('Unexpected MCP tool inventory')
        print('PASS: MCP handshake and nine expected tools', flush=True)
        schema = next(tool['inputSchema'] for tool in tools if tool['name'] == 'flowforge_run')
        task = schema['properties']['input']
        if '$ref' in task:
            task = schema['$defs'][task['$ref'].split('/')[-1]]
        assert task.get('additionalProperties') is False
        assert set(task['properties']) == {'project', 'task_id', 'task_sha256', 'context'}
        context = task['properties']['context']
        assert any(item.get('maxLength') == 5000 for item in context.get('anyOf', [context]))
        print('PASS: actual MCP schema exposes bounded input.context and rejects unknown input fields', flush=True)
        await send({'id': 3, 'method': 'tools/call', 'params': {
            'name': 'homelab_list_services', 'arguments': {
                'session_id': 'deployment-smoke-test',
                'user_request': 'Verify configured tool coverage through MCP and gateway policy',
            },
        }})
        result = await receive(3)
        if result.get('isError'):
            raise RuntimeError('MCP discovery returned an error')
        payload = json.loads(next(item['text'] for item in result['content'] if item['type'] == 'text'))
        if not payload.get('success'):
            raise RuntimeError('Gateway discovery failed: ' + str(payload.get('error', 'UNKNOWN')))
        coverage = payload['data']
        assert set(coverage) == {'coverage', 'services'}
        assert coverage['coverage'] == 'configured_tool_coverage'
        assert all(set(item) == {'service', 'restart'} and
                   item['restart'] in {'AUTO_SAFE', 'CONFIRM', 'DENY'} for item in coverage['services'])
        print('PASS: policy-backed configured tool coverage; no runtime health claims', flush=True)
        await send({'id': 4, 'method': 'tools/call', 'params': {
            'name': 'homelab_inspect_service', 'arguments': {
                'service': 'vaultwarden', 'session_id': 'deployment-smoke-test',
                'user_request': 'Verify read-only Vaultwarden inspection through MCP, gateway and broker',
            },
        }})
        result = await receive(4)
        if result.get('isError'):
            raise RuntimeError('MCP tool returned an error')
        payload = json.loads(next(item['text'] for item in result['content'] if item['type'] == 'text'))
        if not payload.get('success'):
            raise RuntimeError('Gateway tool failed: ' + str(payload.get('error', 'UNKNOWN')))
        print('PASS: Vaultwarden inspection; status=' + str(payload['data'].get('status')), flush=True)
    finally:
        if process.returncode is None:
            process.terminate()
        await process.wait()


if __name__ == '__main__':
    asyncio.run(main())
