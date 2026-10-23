"""Run inside Hermes: native MCP launch, effective platform tools and skill loading.

Use an isolated home/container before deployment; this starts MCP but makes no
personal MCP calls or model requests. Native skill reads may update local caches.
"""
import hashlib
import json
from pathlib import Path

from hermes_cli.config import load_config
from hermes_cli.tools_config import _get_platform_tools
from model_tools import get_tool_definitions
from tools.mcp_tool_discovery import register_mcp_servers
from tools.mcp_tool_lifecycle import shutdown_mcp_servers
from tools.skills_tool import skills_list, skill_view
from tools.cronjob_tools import check_cronjob_requirements
from agent.prompt_builder import build_skills_system_prompt
from toolsets import resolve_toolset, session_disabled_toolsets


def verify_selection(config, personal, platform):
    groups = sorted(_get_platform_tools(config, platform))
    disabled = session_disabled_toolsets(config['agent']['disabled_toolsets'], platform)
    # Use the runtime's schema/availability filtering, not a handwritten union.
    # Inspect both the offered surface and the underlying deferred inventory.
    offered = {t['function']['name'] for t in get_tool_definitions(
        enabled_toolsets=groups, disabled_toolsets=disabled, quiet_mode=True)}
    selected = {t['function']['name'] for t in get_tool_definitions(
        enabled_toolsets=groups, disabled_toolsets=disabled, quiet_mode=True,
        skip_tool_search_assembly=True)}
    required = personal | {'skills_list', 'skill_view', 'memory', 'session_search'}
    # A plain verifier process lacks the interactive/gateway/cron session
    # markers. Respect the native availability check for this existing tool.
    if check_cronjob_requirements():
        required.add('cronjob_manage')
    if platform != 'cron':
        required.add('clarify')
    if selected != required:
        raise RuntimeError(f'{platform}: unexpected effective tool surface; '
                           f'missing={sorted(required - selected)}, extra={sorted(selected - required)}')
    prohibited = {'skill_manage', 'terminal', 'process_manage', 'read_file',
                  'write_file', 'patch', 'search_files', 'execute_code', 'delegate_task'}
    for group in ('terminal', 'file', 'code_execution', 'delegation', 'browser', 'debugging'):
        prohibited.update(resolve_toolset(group))
    if (selected | offered) & prohibited:
        raise RuntimeError(f'{platform}: prohibited tools present')
    if offered - selected - {'tool_search', 'tool_describe', 'tool_call'}:
        raise RuntimeError(f'{platform}: unexpected tools offered by progressive discovery')
    if not {'skills_list', 'skill_view'} <= offered:
        raise RuntimeError(f'{platform}: native skill read tools not offered')
    index = build_skills_system_prompt(available_tools=selected,
        available_toolsets={'skills'})
    if 'homelab-service-diagnosis' not in index:
        raise RuntimeError(f'{platform}: curated skill absent from native system-prompt index')
    print(f'PASS: {platform} effective schemas include native skill reads and all nine personal MCP tools; prohibited tools absent')


def main():
    config = load_config()
    expected = {
        'knowledge_search', 'flowforge_list_workflows',
        'flowforge_list_tasks', 'flowforge_get_run', 'flowforge_run', 'homelab_inspect_service',
        'homelab_list_services', 'homelab_get_logs', 'homelab_restart_service',
    }
    try:
        registered = set(register_mcp_servers(config['mcp_servers']))
        # Hermes releases use either single- or double-underscore MCP prefixes.
        personal = {name for name in registered if name.startswith(('mcp__personal__', 'mcp_personal_'))}
        raw_names = {name.removeprefix('mcp__personal__').removeprefix('mcp_personal_') for name in personal}
        missing = expected - raw_names
        if missing:
            raise RuntimeError('Missing tools in Hermes registration: ' + ', '.join(sorted(missing)))
        if raw_names != expected:
            raise RuntimeError('Unexpected personal MCP inventory')
        print('PASS: Hermes registered all nine personal MCP tools through its filtered subprocess environment')
        for platform in ('cli', 'matrix', 'cron'):
            verify_selection(config, personal, platform)
        assert config['skills']['inline_shell'] is False
        assert config['security']['allow_lazy_installs'] is False
        assert config['curator']['enabled'] is False
        catalog = json.loads(skills_list())
        if 'homelab-service-diagnosis' not in {s['name'] for s in catalog['skills']}:
            raise RuntimeError('Curated skill absent from native discovery')
        skill = json.loads(skill_view('homelab-service-diagnosis'))
        expected_dir = Path('/opt/hermes-curated-skills/homelab-service-diagnosis')
        if not skill.get('success') or Path(skill['skill_dir']).resolve() != expected_dir:
            raise RuntimeError('Curated skill missing or shadowed by another skill')
        if skill['content'] != (expected_dir / 'SKILL.md').read_text():
            raise RuntimeError('Native skill content differs from curated mount')
        print('PASS: native skills_list, prompt index and skill_view discover/load curated external skill; '
              'sha256=' + hashlib.sha256(skill['content'].encode()).hexdigest())
    finally:
        shutdown_mcp_servers()


if __name__ == '__main__':
    main()
