import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { check, object, str, remote } from './common.mjs';
import { openProjectVault, citeProjectResults } from './project-vault.mjs';
const exec = promisify(execFile);
const levels = ['AUTO_SAFE', 'CONFIRM', 'DENY'];
export function validatePolicy(policy) {
  object(policy, ['services', 'workflows', 'projects']);
  for (const [name, item] of Object.entries(policy.services)) {
    check(/^[a-z0-9_-]+$/.test(name));
    object(item, ['container', 'restart']);
    check(/^[a-zA-Z0-9][a-zA-Z0-9_.-]*$/.test(item.container) && levels.includes(item.restart));
  }
  for (const [name, item] of Object.entries(policy.workflows)) {
    check(/^[a-zA-Z0-9_-]+$/.test(name)); object(item, ['permission']); check(levels.includes(item.permission));
  }
  for (const [project, vault] of Object.entries(policy.projects)) check(/^[a-z0-9_-]+$/.test(project) && typeof vault === 'string' && vault.startsWith('/vaults/') && !vault.includes('..'));
  return policy;
}
export function operation(tool, args, policy) {
  if (tool === 'knowledge.search') {
    object(args, ['query', 'project', 'scope', 'limit']); str(args.query);
    if (args.project !== undefined) str(args.project, 100);
    if (args.scope !== undefined) check(Array.isArray(args.scope) && args.scope.length <= 10 && args.scope.every(s => typeof s === 'string' && s.length <= 500));
    if (args.limit !== undefined) check(Number.isInteger(args.limit) && args.limit >= 1 && args.limit <= 10);
    check(Object.hasOwn(policy.projects, args.project || 'default'), 'PROJECT_NOT_CONFIGURED', 404);
    return 'READ';
  }
  if (tool === 'flowforge.listWorkflows') { object(args, []); return 'READ'; }
  if (tool === 'flowforge.listTasks') { object(args, []); return 'READ'; }
  if (tool === 'homelab.listServices') { object(args, []); return 'READ'; }
  if (tool === 'flowforge.getRun') {
    object(args, ['run_id']); check(typeof args.run_id === 'string' && /^[0-9a-f-]{36}$/.test(args.run_id)); return 'READ';
  }
  if (tool === 'flowforge.run') {
    object(args, ['workflow', 'input']); str(args.workflow, 100);
    if (args.input !== undefined) check(args.input && typeof args.input === 'object' && !Array.isArray(args.input));
    check(Object.hasOwn(policy.workflows, args.workflow), 'WORKFLOW_NOT_ALLOWED', 403);
    if (args.workflow === 'task-analysis') {
      object(args.input, ['project', 'task_id', 'task_sha256', 'context']);
      check(args.input.project === 'mentory' && typeof args.input.task_id === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(args.input.task_id));
      check(typeof args.input.task_sha256 === 'string' && /^[a-f0-9]{64}$/.test(args.input.task_sha256));
      if (args.input.context !== undefined) check(typeof args.input.context === 'string' && args.input.context.length <= 5000);
    }
    return policy.workflows[args.workflow].permission;
  }
  check(['homelab.inspectService', 'homelab.getLogs', 'homelab.restartService'].includes(tool), 'UNKNOWN_TOOL', 404);
  object(args, tool === 'homelab.getLogs' ? ['service', 'lines', 'since'] : ['service']); str(args.service, 100);
  check(Object.hasOwn(policy.services, args.service), 'SERVICE_NOT_ALLOWED', 403);
  if (args.lines !== undefined) check(Number.isInteger(args.lines) && args.lines >= 1 && args.lines <= 500);
  if (args.since !== undefined) { str(args.since, 40); check(/^\d{4}-\d\d-\d\dT/.test(args.since) && Number.isFinite(Date.parse(args.since))); }
  return tool === 'homelab.restartService' ? policy.services[args.service].restart : 'READ';
}
export function executor(env, policy) {
  return async (tool, args) => {
    if (tool === 'knowledge.search') {
      check(env.KNOWLEDGE_CLI, 'KNOWLEDGE_NOT_CONFIGURED', 503);
      const project = args.project || 'default';
      let vault = policy.projects[project], manifest;
      if (['mentory', 'homelab'].includes(project)) {
        try { ({vault, manifest} = await openProjectVault(vault, project)); }
        catch { check(false, 'KNOWLEDGE_PROJECT_NOT_READY', 503); }
      }
      const cache = `/state/knowledge-${project}${manifest ? '-' + manifest.snapshotId : ''}.json`;
      const argv = [env.KNOWLEDGE_CLI, 'search', args.query, '--vault', vault, '--cache', cache, '--json', '--limit', String(args.limit || 5)];
      for (const path of args.scope || []) argv.push('--path', path);
      try {
        const {stdout} = await exec(process.execPath, argv, {timeout: 30000, maxBuffer: 131072, env: {PATH: process.env.PATH}});
        const result = JSON.parse(stdout);
        return manifest ? citeProjectResults(result, manifest) : result;
      }
      catch { check(false, 'KNOWLEDGE_FAILED', 502); }
    }
    if (tool === 'flowforge.listWorkflows') return {workflows: Object.entries(policy.workflows).map(([name, p]) => ({name, permission: p.permission}))};
    if (tool === 'homelab.listServices') return {
      coverage: 'configured_tool_coverage',
      services: Object.entries(policy.services).map(([service, item]) => ({service, restart: item.restart})),
    };
    if (['flowforge.listTasks', 'flowforge.getRun'].includes(tool)) {
      check(env.FLOWFORGE_URL && env.FLOWFORGE_TOKEN, 'FLOWFORGE_NOT_CONFIGURED', 503);
      const route = tool === 'flowforge.listTasks' ? '/tasks' : `/runs/${args.run_id}`;
      return remote(env.FLOWFORGE_URL + route, env.FLOWFORGE_TOKEN, undefined, 'GET');
    }
    if (tool === 'flowforge.run') {
      check(env.FLOWFORGE_URL && env.FLOWFORGE_TOKEN, 'FLOWFORGE_NOT_CONFIGURED', 503);
      const result = await remote(env.FLOWFORGE_URL + '/run', env.FLOWFORGE_TOKEN, args);
      check(result.success === true, 'WORKFLOW_FAILED', 502); return result;
    }
    return remote(`${env.BROKER_URL}/execute`, env.BROKER_TOKEN, {tool, arguments: args});
  };
}
