// Explicit local refresh or read-only freshness check; no deployment or scheduling.
import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import { buildHomelabVault, checkHomelabVault } from '../apps/flowforge-gateway/src/homelab-vault.mjs';

const {values} = parseArgs({options: {project: {type:'string'}, output: {type:'string'}, check: {type:'boolean'}}});
if (!values.project || !values.output) throw new Error('Usage: node scripts/build_homelab_knowledge.mjs --project PATH --output PATH [--check]');
try {
  const options = {project:resolve(values.project), destination:resolve(values.output)};
  const result = await (values.check ? checkHomelabVault(options) : buildHomelabVault(options));
  console.log(JSON.stringify(result));
  if (values.check && !result.ready) process.exitCode = 1;
} catch (error) {
  console.error(JSON.stringify({ready:false, error:error.code || error.message}));
  process.exitCode = 1;
}
