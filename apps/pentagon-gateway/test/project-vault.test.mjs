import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { buildProjectVault, openProjectVault, citeProjectResults } from '../src/project-vault.mjs';

async function fixture(t) {
  const root = await mkdtemp(resolve(tmpdir(), 'project-vault-'));
  t.after(() => rm(root, {recursive:true, force:true}));
  const project = resolve(root, 'project'), output = resolve(root, 'projection'), queue = resolve(root, 'queue.jsonl');
  const done = resolve(project, '.opencode/tasks/completed'), future = resolve(project, '.opencode/tasks/future');
  await mkdir(done, {recursive:true}); await mkdir(future, {recursive:true});
  await writeFile(resolve(project, 'README.md'), '# Mentory\nLearning platform.\n');
  await writeFile(resolve(project, 'SUMMARY.md'), '# Project history\n## Certificates\nCertificates are downloaded after path completion.\n');
  await writeFile(resolve(done, 'task.md'), '# Completion certificates\n\nImplement certificate eligibility for completed learning paths.\n');
  await writeFile(resolve(done, 'contract-decisions.md'), '# Certificate decisions\n\n## Certificate eligibility\nIssue a completion certificate only after all required courses are complete.\n');
  await writeFile(resolve(done, 'concept-plan.md'), '# Certificate planning\n\nConsider a PDF certificate.\n');
  await writeFile(resolve(future, 'task.md'), '# Future payments\nNot implemented.\n');
  const tasks = [{id:'example-done', status:'done', task_file:resolve(done,'task.md')}, {id:'example-future', status:'todo', task_file:resolve(future,'task.md')}];
  await writeFile(queue, tasks.map(task => JSON.stringify(task)).join('\n'));
  return {root, project, queue, output, done, tasks};
}

test('projection includes completed task evidence, preserves source bytes, and labels plans separately', async t => {
  const f = await fixture(t);
  const original = await readFile(resolve(f.done, 'contract-decisions.md'), 'utf8');
  const result = await buildProjectVault({...f, destination:f.output});
  assert.equal(result.completedTasks, 1); assert.equal(result.documents, 5);
  const {vault, manifest} = await openProjectVault(f.output);
  assert.ok(!Object.keys(manifest.documents).some(path => path.includes('example-future')));
  const path = 'mentory/task-example-done/references/contract-decisions.md';
  const entry = manifest.documents[path];
  assert.equal(entry.kind, 'decision-record');
  assert.equal(manifest.documents['mentory/task-example-done/references/concept-plan.md'].kind, 'planning');
  const projected = await readFile(resolve(vault,path), 'utf8');
  assert.equal(projected.split('\n').slice(entry.lineOffset).join('\n'), original);
  const cited = citeProjectResults({results:[{path,content:'## Certificate eligibility\nIssue a completion certificate only after all required courses are complete.',startLine:3+entry.lineOffset,endLine:4+entry.lineOffset}]},manifest);
  assert.equal(cited.results[0].source.reference, '.opencode/tasks/completed/contract-decisions.md:3');
  assert.equal(cited.results[0].source.endLine, 4);
  assert.equal(cited.results[0].source.taskStatus, 'done');
  assert.equal(await readFile(resolve(f.done,'contract-decisions.md'),'utf8'), original);
});

test('source refresh changes snapshot identity and unchanged rebuilds reuse the same snapshot', async t => {
  const f = await fixture(t);
  const first = await buildProjectVault({...f,destination:f.output});
  assert.equal((await buildProjectVault({...f,destination:f.output})).snapshotId,first.snapshotId);
  await writeFile(resolve(f.done,'contract-decisions.md'),'# New certificate decision\nUse verifiable completion.\n');
  const next = await buildProjectVault({...f,destination:f.output});
  assert.notEqual(next.snapshotId,first.snapshotId);
  assert.equal((await openProjectVault(f.output)).manifest.snapshotId,next.snapshotId);
});

test('projection rejects source escapes, symlinked documents and tampered snapshot pointers', async t => {
  const f = await fixture(t);
  await symlink(resolve(f.project,'README.md'),resolve(f.done,'escape.md'));
  await assert.rejects(buildProjectVault({...f,destination:f.output}), /UNSAFE_KNOWLEDGE_SOURCE/);
  await rm(resolve(f.done,'escape.md'));
  await writeFile(f.queue,JSON.stringify({...f.tasks[0],task_file:resolve(f.project,'README.md')}));
  await assert.rejects(buildProjectVault({...f,destination:f.output}), /UNSAFE_KNOWLEDGE_SOURCE/);
  await mkdir(f.output,{recursive:true});
  await writeFile(resolve(f.output,'current.json'),JSON.stringify({snapshotId:'../escape'}));
  await assert.rejects(openProjectVault(f.output), /INVALID_KNOWLEDGE_SNAPSHOT/);
});

test('actual existing Knowledge Router retrieves projected decisions with original line citations', async t => {
  const cli = process.env.KNOWLEDGE_CLI || resolve(import.meta.dirname,'../../../../apps/knowledge-router/dist/cli.js');
  try {await readFile(cli);} catch {return t.skip('Existing Knowledge Router checkout is not built');}
  const f = await fixture(t);
  await buildProjectVault({...f,destination:f.output});
  const {vault,manifest} = await openProjectVault(f.output);
  const {stdout} = await promisify(execFile)(process.execPath,[cli,'search','certificate eligibility required courses completion','--vault',vault,'--cache',resolve(f.root,'index.json'),'--json']);
  const result = citeProjectResults(JSON.parse(stdout),manifest);
  assert.ok(result.results.some(item => item.source.kind === 'decision-record' && item.content.includes('all required courses')));
  assert.ok(result.results.every(item => item.source.sha256.length === 64 && item.source.startLine >= 1));
  const primary = result.results.find(item => item.kind === 'skill');
  assert.ok(primary.content.startsWith('# Completion certificates'));
});
