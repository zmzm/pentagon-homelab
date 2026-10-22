// Allowlisted documentation projection only. Knowledge Router still owns all retrieval.
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { readFile, readdir, realpath, stat } from 'node:fs/promises';
import { resolve } from 'node:path';
import { check } from './common.mjs';
import { openProjectVault, publishProjectVault, snapshotMetadata } from './project-vault.mjs';

const exec = promisify(execFile);
const hash = content => createHash('sha256').update(content).digest('hex');
export const HOMELAB_DOCUMENTS = Object.freeze([
  'README.md', 'ARCHITECTURE.md', 'SERVICES.md', 'DOMAINS.md', 'OPERATIONS.md',
  'RECOVERY_CHECKLIST.md', 'monitoring/README.md', 'apps/hermes/README.md',
]);
const incident = path => /^incidents\/[^/]+\.md$/.test(path);

async function prepare(project) {
  project = await realpath(project);
  const incidents = resolve(project, 'incidents');
  check(await realpath(incidents) === incidents, 'UNSAFE_KNOWLEDGE_SOURCE');
  // Non-recursive: incidents/*.md, never arbitrary Markdown elsewhere in the repo.
  const paths = [...HOMELAB_DOCUMENTS, ...(await readdir(incidents)).filter(name => !name.startsWith('.') && name.endsWith('.md'))
    .map(name => `incidents/${name}`)].sort();
  const sources = [];
  let bytes = 0;
  for (const path of paths) {
    const absolute = resolve(project, path);
    check(await realpath(absolute) === absolute, 'UNSAFE_KNOWLEDGE_SOURCE');
    const info = await stat(absolute);
    check(info.isFile(), 'UNSAFE_KNOWLEDGE_SOURCE');
    check(info.size <= 131072, 'KNOWLEDGE_SOURCE_TOO_LARGE');
    const content = await readFile(absolute, 'utf8');
    bytes += Buffer.byteLength(content);
    check(bytes <= 16777216 && sources.length < 2000, 'KNOWLEDGE_SNAPSHOT_TOO_LARGE');
    sources.push({path, content, sha256: hash(content), kind: incident(path) ? 'historical-incident' : 'operational-document'});
  }
  let gitCommit = null, documentationDirty = null;
  try {
    gitCommit = (await exec('git', ['-C', project, 'rev-parse', 'HEAD'])).stdout.trim();
    check(/^[a-f0-9]{40,64}$/.test(gitCommit), 'INVALID_SOURCE_VERSION');
    documentationDirty = Boolean((await exec('git', ['-C', project, 'status', '--porcelain', '--untracked-files=all', '--', ...paths])).stdout.trim());
  } catch { gitCommit = null; documentationDirty = null; }
  const sourceVersion = {repository: 'zmzm/pentagon-homelab', gitCommit, documentationDirty};
  const topics = content => content.split(/\r?\n/).filter(line => /^#{1,6}\s/.test(line))
    .map(line => line.replace(/^#+\s*/, '').slice(0,160)).slice(0,80);
  const prepared = sources.map(source => {
    const historical = incident(source.path);
    // Keep incident evidence in separate skills; current instructions cannot pull historical references.
    const primary = historical || source.path === 'README.md';
    const projected = historical ? `homelab/incident-${source.path.slice(10,-3)}/SKILL.md`
      : primary ? 'homelab/operations/SKILL.md' : `homelab/operations/references/${source.path}`;
    const header = `---\nkind: ${primary ? 'skill' : 'reference'}\ntopics: ${JSON.stringify(topics(source.content))}\n---\n`;
    return [projected, {...source, content: header + source.content, lineOffset: header.split('\n').length - 1}];
  });
  const snapshotId = hash(JSON.stringify({version: 1, project: 'homelab', sourceVersion, documents: prepared}));
  return {prepared, bytes, metadata: {version: 1, project: 'homelab', snapshotId, sourceVersion,
    generatedAt: new Date().toISOString()}};
}

export async function buildHomelabVault({project, destination}) {
  const {prepared, bytes, metadata} = await prepare(project);
  await publishProjectVault(destination, prepared, metadata);
  return {snapshotId: metadata.snapshotId, documents: prepared.length, sourceBytes: bytes, sourceVersion: metadata.sourceVersion};
}

// Operator-side comparison reads live docs. Gateway intentionally has no repository mount.
export async function checkHomelabVault({project, destination}) {
  let manifest;
  try { ({manifest} = await openProjectVault(destination, 'homelab')); }
  catch { return {ready: false, reason: 'KNOWLEDGE_PROJECT_NOT_READY'}; }
  const {metadata} = await prepare(project);
  const snapshot = snapshotMetadata(manifest);
  const sourceChanged = manifest.snapshotId !== metadata.snapshotId;
  return {ready: !sourceChanged && !snapshot.stale, sourceChanged, sourceSnapshot: snapshot};
}
