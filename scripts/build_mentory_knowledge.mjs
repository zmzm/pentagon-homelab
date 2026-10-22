// Explicit source refresh; never modifies the project or production task queue.
import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import { buildProjectVault } from '../apps/flowforge-gateway/src/project-vault.mjs';

const {values} = parseArgs({options: {project: {type:'string'}, queue: {type:'string'}, output: {type:'string'}}});
if (!values.project || !values.queue || !values.output) throw new Error('Usage: node scripts/build_mentory_knowledge.mjs --project PATH --queue PATH --output PATH');
console.log(JSON.stringify(await buildProjectVault({project:resolve(values.project), queue:resolve(values.queue), destination:resolve(values.output)})));
