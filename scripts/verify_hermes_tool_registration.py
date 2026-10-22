"""Run inside Hermes to verify its own MCP launch path and Matrix tool selection."""
from hermes_cli.config import load_config

from tools.mcp_tool_discovery import register_mcp_servers
from tools.mcp_tool_lifecycle import shutdown_mcp_servers
from toolsets import resolve_toolset


def main():
    config = load_config()
    expected = {
        'knowledge_search', 'flowforge_list_workflows',
        'flowforge_list_tasks', 'flowforge_get_run', 'flowforge_run', 'homelab_inspect_service',
        'homelab_get_logs', 'homelab_restart_service',
    }
    try:
        registered = set(register_mcp_servers(config['mcp_servers']))
        # Hermes releases use either single- or double-underscore MCP prefixes.
        personal = {name for name in registered if name.startswith(('mcp__personal__', 'mcp_personal_'))}
        raw_names = {name.removeprefix('mcp__personal__').removeprefix('mcp_personal_') for name in personal}
        missing = expected - raw_names
        if missing:
            raise RuntimeError('Missing tools in Hermes registration: ' + ', '.join(sorted(missing)))
        selected = set()
        for group in config['platform_toolsets']['matrix']:
            selected.update(resolve_toolset(group))
        for group in config['agent']['disabled_toolsets']:
            selected.difference_update(resolve_toolset(group))
        missing = personal - selected
        if missing:
            raise RuntimeError('Missing tools in Matrix selection: ' + ', '.join(sorted(missing)))
        prohibited = {'terminal', 'process_manage', 'read_file', 'write_file', 'patch',
                      'execute_code', 'delegate_task', 'browser_navigate'}
        if selected & prohibited:
            raise RuntimeError('Prohibited tools present in Matrix selection')
        print('PASS: Hermes registered all eight personal MCP tools through its filtered subprocess environment')
        print('PASS: Matrix selection includes all eight tools and excludes shell/file/code/delegation tools')
    finally:
        shutdown_mcp_servers()


if __name__ == '__main__':
    main()
