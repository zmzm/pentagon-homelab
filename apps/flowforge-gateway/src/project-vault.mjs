// Project-specific source projection. Ranking and retrieval remain Knowledge Router's.
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, readdir, realpath, rename, rm, stat, writeFile } from 'node:fs/promises';
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path';
import { check } from './common.mjs';

const hash = text => createHash('sha256').update(text).digest('hex');
const inside = (root, path) => path === root || path.startsWith(root + sep);
const kind = name => /contract|decision|adr/i.test(name) ? 'decision-record'
  : /concept|grounded/i.test(name) ? 'planning'
  : /execution|implementation|verification/i.test(name) ? 'execution-record' : 'project-notes';

export async function buildProjectVault({project, queue, destination}) {
  project = await realpath(project);
  const tasksRoot = resolve(project, '.opencode/tasks');
  check(await realpath(tasksRoot) === tasksRoot, 'UNSAFE_KNOWLEDGE_SOURCE');
  const rows = (await readFile(queue, 'utf8')).trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
  const entries = new Map();
  let bytes = 0;
  async function source(path, projected, sourceKind, task) {
    check(inside(project, path) && await realpath(path) === path, 'UNSAFE_KNOWLEDGE_SOURCE');
    const info = await stat(path);
    check(info.isFile() && info.size <= 131072, 'KNOWLEDGE_SOURCE_TOO_LARGE');
    const content = await readFile(path, 'utf8');
    bytes += Buffer.byteLength(content);
    check(bytes <= 16777216 && entries.size < 2000, 'KNOWLEDGE_SNAPSHOT_TOO_LARGE');
    entries.set(projected, {content, path: relative(project, path).split(sep).join('/'),
      kind: sourceKind, taskId: task?.id, taskStatus: task?.status, sha256: hash(content)});
  }
  await source(resolve(project, 'README.md'), 'mentory/overview/SKILL.md', 'project-overview');
  await source(resolve(project, 'SUMMARY.md'), 'mentory/overview/references/SUMMARY.md', 'project-history');
  const ids = new Set();
  for (const task of rows.filter(row => row.status === 'done')) {
    check(typeof task.id === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(task.id) && !ids.has(task.id), 'INVALID_KNOWLEDGE_TASK');
    ids.add(task.id);
    check(typeof task.task_file === 'string', 'INVALID_KNOWLEDGE_TASK');
    const taskFile = resolve(project, task.task_file);
    check(inside(tasksRoot, taskFile) && await realpath(taskFile) === taskFile, 'UNSAFE_KNOWLEDGE_SOURCE');
    const directory = dirname(taskFile);
    const prefix = `mentory/task-${task.id}`;
    await source(taskFile, `${prefix}/SKILL.md`, 'task-requirements', task);
    // Only Markdown siblings of a completed task; no repository, credentials or agent prompts.
    for (const entry of (await readdir(directory, {withFileTypes: true})).sort((a,b) => a.name.localeCompare(b.name))) {
      const path = resolve(directory, entry.name);
      if (path === taskFile || entry.name.startsWith('.') || !/\.md$/i.test(entry.name)) continue;
      check(entry.isFile(), 'UNSAFE_KNOWLEDGE_SOURCE');
      await source(path, `${prefix}/references/${entry.name}`, kind(entry.name), task);
    }
  }
  // Metadata exposes headings to the existing router without building another retriever.
  const topics = new Map();
  for (const [path, entry] of entries) {
    const group = path.split('/').slice(0,2).join('/');
    const headings = entry.content.split(/\r?\n/).filter(line => /^#{1,6}\s/.test(line)).map(line => line.replace(/^#+\s*/, '').slice(0,160));
    topics.set(group, [...new Set([...(topics.get(group) || []), ...headings])].slice(0,80));
  }
  const prepared = [...entries].sort(([a],[b]) => a.localeCompare(b)).map(([path, entry]) => {
    const group = path.split('/').slice(0,2).join('/');
    const localTopics = entry.content.split(/\r?\n/).filter(line => /^#{1,6}\s/.test(line)).map(line => line.replace(/^#+\s*/, '').slice(0,160)).slice(0,80);
    const header = `---\nkind: ${path.endsWith('/SKILL.md') ? 'skill' : 'reference'}\ntopics: ${JSON.stringify(path.endsWith('/SKILL.md') ? topics.get(group) : localTopics)}\n---\n`;
    return [path, {...entry, content: header + entry.content, lineOffset: header.split('\n').length - 1}];
  });
  const snapshotId = hash(JSON.stringify({version: 1, project, documents: prepared}));
  const snapshot = resolve(destination, 'snapshots', snapshotId);
  await mkdir(resolve(destination, 'snapshots'), {recursive: true, mode: 0o700});
  const stage = resolve(destination, 'snapshots', `.build-${randomUUID()}`);
  await mkdir(stage, {mode: 0o700});
  const documents = {};
  try {
    for (const [path, entry] of prepared) {
      const output = resolve(stage, 'vault', path);
      await mkdir(dirname(output), {recursive: true, mode: 0o700});
      await writeFile(output, entry.content, {mode: 0o600});
      const {content: _content, ...metadata} = entry;
      documents[path] = metadata;
    }
    const manifest = {version: 1, project: 'mentory', sourceRoot: project, snapshotId,
      generatedAt: new Date().toISOString(), documents};
    await writeFile(resolve(stage, 'manifest.json'), JSON.stringify(manifest), {mode: 0o600});
    try { await rename(stage, snapshot); }
    catch (error) {
      if (!['EEXIST','ENOTEMPTY'].includes(error.code)) throw error;
      await rm(stage, {recursive: true});
    }
    const pointer = resolve(destination, `.current-${randomUUID()}.json`);
    await writeFile(pointer, JSON.stringify({snapshotId}), {mode: 0o600});
    await rename(pointer, resolve(destination, 'current.json'));
    return {snapshotId, documents: prepared.length, completedTasks: ids.size, sourceBytes: bytes};
  } catch (error) { await rm(stage, {recursive: true, force: true}); throw error; }
}

export async function openProjectVault(root) {
  const pointer = JSON.parse(await readFile(resolve(root, 'current.json'), 'utf8'));
  check(typeof pointer.snapshotId === 'string' && /^[a-f0-9]{64}$/.test(pointer.snapshotId), 'INVALID_KNOWLEDGE_SNAPSHOT');
  const snapshot = resolve(root, 'snapshots', pointer.snapshotId);
  check(await realpath(snapshot) === snapshot, 'INVALID_KNOWLEDGE_SNAPSHOT');
  const manifest = JSON.parse(await readFile(resolve(snapshot, 'manifest.json'), 'utf8'));
  check(manifest.version === 1 && manifest.project === 'mentory' && manifest.snapshotId === pointer.snapshotId, 'INVALID_KNOWLEDGE_SNAPSHOT');
  return {vault: resolve(snapshot, 'vault'), manifest};
}

export function citeProjectResults(response, manifest) {
  return {...response, sourceSnapshot: {project: manifest.project, id: manifest.snapshotId,
    generatedAt: manifest.generatedAt, completedTasksOnly: true}, results: response.results.map(result => {
    const source = manifest.documents[result.path];
    check(source && !isAbsolute(source.path) && !source.path.split('/').includes('..'), 'INVALID_KNOWLEDGE_CITATION');
    const startLine = Math.max(1, result.startLine - source.lineOffset);
    const endLine = Math.max(startLine, result.endLine - source.lineOffset);
    let content = result.content;
    if (result.startLine === 1) content = content.split('\n').slice(source.lineOffset).join('\n');
    const {lineOffset: _lineOffset, ...citation} = source;
    return {...result, content, source: {project: 'mentory', ...citation, startLine, endLine,
      reference: `${source.path}:${startLine}`}};
  })};
}
