import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, readdir, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { HOMELAB_DOCUMENTS, buildHomelabVault, checkHomelabVault } from '../src/homelab-vault.mjs';
import { openProjectVault, citeProjectResults, snapshotMetadata, HOMELAB_MAX_AGE_SECONDS } from '../src/project-vault.mjs';
import { executor, operation, validatePolicy } from '../src/operations.mjs';

const exec = promisify(execFile);
const repo = resolve(import.meta.dirname, '../../..');
const cli = process.env.KNOWLEDGE_CLI || resolve(repo, '../apps/knowledge-router/dist/cli.js');

async function fixture(t) {
  const root = await mkdtemp(resolve(tmpdir(), 'homelab-vault-'));
  t.after(() => rm(root, {recursive:true, force:true}));
  const project = resolve(root, 'project'), destination = resolve(root, 'projection');
  const files = [...HOMELAB_DOCUMENTS, 'incidents/2026-03-08-dns-loop.md', 'incidents/.hidden.md'];
  for (const path of files) {
    await mkdir(dirname(resolve(project,path)), {recursive:true});
    await writeFile(resolve(project,path), `# ${path}\n\nExact source content for ${path}.\n`);
  }
  return {root, project, destination};
}

test('homelab selects exactly the allowlist, preserves bytes and distinguishes history', async t => {
  assert.deepEqual([...HOMELAB_DOCUMENTS], ['README.md', 'ARCHITECTURE.md', 'SERVICES.md', 'DOMAINS.md',
    'OPERATIONS.md', 'RECOVERY_CHECKLIST.md', 'monitoring/README.md', 'apps/hermes/README.md']);
  const f = await fixture(t);
  const excluded = ['ACTION_LIST.md', 'INCIDENT_TEMPLATE.md', 'ansible/README.md', 'apps/matrix/README.md',
    'data/private.md', 'backups/private.md', 'reports/private.md', 'apps/hermes/.env',
    'incidents/nested/private.md', 'incidents/private.txt'];
  for (const path of excluded) {
    await mkdir(dirname(resolve(f.project,path)), {recursive:true});
    await writeFile(resolve(f.project,path), 'EXCLUDED_SENTINEL');
  }
  // Even symlinks outside the allowlist must not be traversed.
  await symlink('/etc', resolve(f.project,'data/escape'));
  await buildHomelabVault(f);
  const {vault,manifest} = await openProjectVault(f.destination, 'homelab');
  assert.deepEqual(Object.values(manifest.documents).map(s => s.path).sort(),
    [...HOMELAB_DOCUMENTS, 'incidents/2026-03-08-dns-loop.md'].sort());
  for (const [path,source] of Object.entries(manifest.documents)) {
    const content = await readFile(resolve(vault,path), 'utf8');
    assert.equal(content.split('\n').slice(source.lineOffset).join('\n'), await readFile(resolve(f.project,source.path),'utf8'));
    assert.ok(!content.includes('EXCLUDED_SENTINEL'));
    assert.equal(source.kind, source.path.startsWith('incidents/') ? 'historical-incident' : 'operational-document');
    if (source.kind === 'historical-incident') assert.ok(!path.startsWith('homelab/operations/'));
  }
});

test('snapshot version records committed revision and dirty selected docs, ignoring excluded changes', async t => {
  const f = await fixture(t);
  await exec('git',['-C',f.project,'init','--quiet']);
  await exec('git',['-C',f.project,'add','.']);
  await exec('git',['-C',f.project,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Fixture docs']);
  const first = await buildHomelabVault(f);
  assert.match(first.sourceVersion.gitCommit,/^[a-f0-9]{40,64}$/);
  assert.equal(first.sourceVersion.documentationDirty,false);
  await writeFile(resolve(f.project,'outside.md'),'Excluded new file');
  assert.equal((await checkHomelabVault(f)).ready,true);
  await writeFile(resolve(f.project,'README.md'),'# Changed docs');
  assert.equal((await checkHomelabVault(f)).sourceChanged,true);
  const dirty = await buildHomelabVault(f);
  assert.equal(dirty.sourceVersion.gitCommit,first.sourceVersion.gitCommit);
  assert.equal(dirty.sourceVersion.documentationDirty,true);
});

test('citations remove generated headers and preserve original ranges, hashes and snapshot version', async t => {
  const f = await fixture(t); await buildHomelabVault(f);
  const {vault,manifest} = await openProjectVault(f.destination,'homelab');
  for (const [path,source] of Object.entries(manifest.documents)) {
    const original = await readFile(resolve(f.project,source.path),'utf8');
    const result = citeProjectResults({results:[{path, startLine:1, endLine:source.lineOffset+4,
      content:await readFile(resolve(vault,path),'utf8')},
    {path, startLine:source.lineOffset+3, endLine:source.lineOffset+3, content:original.split('\n')[2]}]},manifest);
    assert.equal(result.results[0].content, original);
    assert.equal(result.results[0].source.reference, `${source.path}:1`);
    assert.equal(result.results[0].source.endLine, 4);
    assert.equal(result.results[1].source.reference, `${source.path}:3`);
    assert.equal(result.results[1].source.sha256.length, 64);
    assert.equal(result.results[1].source.project, 'homelab');
    assert.equal(result.sourceSnapshot.id, manifest.snapshotId);
    assert.equal(result.sourceSnapshot.repository, 'zmzm/pentagon-homelab');
    assert.equal(result.sourceSnapshot.version, 1);
    assert.equal(result.sourceSnapshot.currentStateVerified, false);
  }
  assert.throws(() => citeProjectResults({results:[{path:'outside.md'}]},manifest), /INVALID_KNOWLEDGE_CITATION/);
});

test('refresh detects changes, addition/deletion of incidents, missing and stale snapshots; failed builds retain pointer', async t => {
  const f = await fixture(t);
  assert.equal((await checkHomelabVault(f)).reason, 'KNOWLEDGE_PROJECT_NOT_READY');
  const first = await buildHomelabVault(f);
  assert.equal((await checkHomelabVault(f)).ready, true);
  assert.equal((await buildHomelabVault(f)).snapshotId, first.snapshotId);
  await writeFile(resolve(f.project,'outside.md'), 'Excluded change');
  assert.equal((await checkHomelabVault(f)).ready, true);
  await writeFile(resolve(f.project,'OPERATIONS.md'), '# Revised database backups\nHourly logical dumps.\n');
  assert.equal((await checkHomelabVault(f)).sourceChanged, true);
  const next = await buildHomelabVault(f);
  assert.notEqual(next.snapshotId, first.snapshotId);
  assert.ok((await readdir(resolve(f.destination,'snapshots'))).includes(first.snapshotId));
  await writeFile(resolve(f.project,'incidents/new.md'), '# New historical incident');
  assert.equal((await checkHomelabVault(f)).sourceChanged, true);
  await buildHomelabVault(f);
  await rm(resolve(f.project,'incidents/new.md'));
  assert.equal((await checkHomelabVault(f)).sourceChanged, true);
  await buildHomelabVault(f);
  const pointer = resolve(f.destination,'current.json');
  await writeFile(pointer,JSON.stringify({snapshotId:next.snapshotId,refreshedAt:'2000-01-01T00:00:00Z'}));
  assert.equal((await checkHomelabVault(f)).ready, false);
  assert.equal((await checkHomelabVault(f)).sourceSnapshot.stale, true);
  await buildHomelabVault(f); // Revalidating identical bytes renews refreshedAt, not immutable generatedAt.
  assert.equal((await checkHomelabVault(f)).ready, true);
  const {manifest} = await openProjectVault(f.destination,'homelab');
  assert.equal(snapshotMetadata(manifest,Date.parse(manifest.refreshedAt)+(HOMELAB_MAX_AGE_SECONDS+1)*1000).stale,true);
  const before = await readFile(pointer,'utf8');
  await rm(resolve(f.project,'README.md'));
  await assert.rejects(buildHomelabVault(f), /ENOENT/);
  assert.equal(await readFile(pointer,'utf8'),before);
  const {stdout} = await exec(process.execPath,[resolve(repo,'scripts/build_homelab_knowledge.mjs'),
    '--project',f.project,'--output',resolve(f.root,'missing'),'--check']).catch(e => e);
  assert.equal(JSON.parse(stdout).reason,'KNOWLEDGE_PROJECT_NOT_READY');
});

test('symlinked selected documents/directories, oversized docs, and wrong-project snapshots fail closed', async t => {
  const f = await fixture(t); await buildHomelabVault(f);
  await assert.rejects(openProjectVault(f.destination,'mentory'), /INVALID_KNOWLEDGE_SNAPSHOT/);
  await rm(resolve(f.project,'README.md'));
  await symlink(resolve(f.project,'ARCHITECTURE.md'),resolve(f.project,'README.md'));
  await assert.rejects(buildHomelabVault(f), /UNSAFE_KNOWLEDGE_SOURCE/);
  await rm(resolve(f.project,'README.md'));
  await writeFile(resolve(f.project,'README.md'), 'x'.repeat(131073));
  await assert.rejects(buildHomelabVault(f), /KNOWLEDGE_SOURCE_TOO_LARGE/);
  await writeFile(resolve(f.project,'README.md'), '# Homelab');
  await symlink(resolve(f.project,'README.md'),resolve(f.project,'incidents/escape.md'));
  await assert.rejects(buildHomelabVault(f), /UNSAFE_KNOWLEDGE_SOURCE/);
  await rm(resolve(f.project,'incidents'),{recursive:true});
  await symlink(resolve(f.project,'monitoring'),resolve(f.project,'incidents'));
  await assert.rejects(buildHomelabVault(f), /UNSAFE_KNOWLEDGE_SOURCE/);
});

test('project selection uses distinct vaults and snapshot caches, forwards scope, and never falls back on missing homelab', async t => {
  const f = await fixture(t); const built = await buildHomelabVault(f);
  const policy = {services:{},workflows:{},projects:{homelab:f.destination,mentory:f.destination,default:resolve(f.root,'coding')}};
  const fakeCli = resolve(f.root,'cli.mjs');
  await writeFile(fakeCli, 'console.log(JSON.stringify({argv:process.argv.slice(2),results:[]}))');
  const execute = executor({KNOWLEDGE_CLI:fakeCli},policy);
  const args = {query:'Matrix',project:'homelab',scope:['OPERATIONS.md'],limit:3};
  assert.equal(operation('knowledge.search',args,policy),'READ');
  const response = await execute('knowledge.search',args);
  assert.ok(response.argv.includes(resolve(f.destination,'snapshots',built.snapshotId,'vault')));
  assert.ok(response.argv.includes(`/state/knowledge-homelab-${built.snapshotId}.json`));
  assert.deepEqual(response.argv.slice(-2),['--path','OPERATIONS.md']);
  await writeFile(resolve(f.project,'OPERATIONS.md'),'# Changed operations\nNew source version.');
  const refreshed = await buildHomelabVault(f);
  const afterRefresh = await execute('knowledge.search',args);
  assert.ok(afterRefresh.argv.includes(`/state/knowledge-homelab-${refreshed.snapshotId}.json`));
  assert.ok(!afterRefresh.argv.includes(`/state/knowledge-homelab-${built.snapshotId}.json`));
  const coding = await execute('knowledge.search',{query:'coding',project:'default'});
  assert.ok(coding.argv.includes(policy.projects.default)); assert.equal(coding.sourceSnapshot,undefined);
  await assert.rejects(execute('knowledge.search',{query:'x',project:'mentory'}), /KNOWLEDGE_PROJECT_NOT_READY/);
  policy.projects.homelab = resolve(f.root,'missing');
  await assert.rejects(execute('knowledge.search',args), /KNOWLEDGE_PROJECT_NOT_READY/);
  assert.throws(() => operation('knowledge.search',{query:'x',project:'unknown'},policy), /PROJECT_NOT_CONFIGURED/);
  const configured = validatePolicy(JSON.parse(await readFile(resolve(repo,'apps/flowforge-gateway/policy.example.json'),'utf8')));
  assert.deepEqual(configured.projects,{mentory:'/vaults/mentory',default:'/vaults/coding',homelab:'/vaults/homelab'});
});

test('actual Knowledge Router retrieves all three representative questions from repository docs with exact citations', async t => {
  try { await readFile(cli); } catch { return t.skip('Actual Knowledge Router CLI unavailable; fixture tests do not prove retrieval'); }
  const f = await fixture(t);
  await buildHomelabVault({project:repo,destination:f.destination});
  const {vault,manifest} = await openProjectVault(f.destination,'homelab');
  const examples = [
    ['How is Matrix exposed externally?', /Cloudflare Tunnel/, 'operational-document'],
    ['How are Matrix database backups configured?', /homelab-matrix-backup\.timer/, 'operational-document'],
    ['What happened during the DNS loop incident?', /Conditional forwarding/, 'historical-incident'],
  ];
  for (const [query,evidence,kind] of examples) {
    const {stdout} = await exec(process.execPath,[cli,'search',query,'--vault',vault,'--cache',resolve(f.root,'index.json'),'--json']);
    const result = citeProjectResults(JSON.parse(stdout),manifest);
    assert.ok(result.results.some(r => r.source.kind === kind && evidence.test(r.content)), `Missing evidence: ${query}`);
    if (kind === 'operational-document') assert.ok(result.results.every(r => r.source.kind !== 'historical-incident'));
    for (const item of result.results) {
      const original = await readFile(resolve(repo,item.source.path),'utf8');
      assert.equal(item.content, original.split(/\r?\n/).slice(item.source.startLine-1,item.source.endLine).join('\n'));
    }
    t.diagnostic(JSON.stringify({query,snapshot:result.sourceSnapshot, citations:result.results.map(r => r.source.reference)}));
  }
});
