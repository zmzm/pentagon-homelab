import test from 'node:test';
import assert from 'node:assert/strict';
import { ApprovalRelay, decisionFor } from '../src/matrix-approvals.mjs';

const id = '12345678-1234-1234-1234-123456789abc';
const room = '!hermes:server'; const user = '@owner:server'; const now = 1000000;
const prompts = {[id]: {eventId: '$prompt', preparedAt: now - 1000, expiresAt: now + 10000}};
const event = {type: 'm.room.message', sender: user, event_id: '$decision', origin_server_ts: now, content: {msgtype: 'm.text', body: `!approve ${id}`}};

test('only fresh explicit unedited commands from an allowed user in the approval room qualify', () => {
  assert.equal(decisionFor(event, room, room, [user], prompts, now).approve, true);
  for (const input of [
    {...event, sender: '@bot:server'},
    {...event, origin_server_ts: now - 5000},
    {...event, origin_server_ts: now + 60001},
    {...event, content: {...event.content, body: 'yes'}},
    {...event, content: {...event.content, 'm.relates_to': {rel_type: 'm.replace'}}},
    {...event, unsigned: {redacted_because: {}}},
    {...event, content: {...event.content, body: `!approve ${id} and restart everything`}},
  ]) assert.equal(decisionFor(input, room, room, [user], prompts, now), null);
  assert.equal(decisionFor(event, '!other:server', room, [user], prompts, now), null);
  assert.equal(decisionFor(event, room, room, [user], {}, now), null);
});

function fixture({encrypted = false, limited = false, status = 'PENDING'} = {}) {
  const state = {since: 'initial', prompts: {}}; const sends = [], decisions = [], executions = [], logs = [];
  let events = [];
  const record = {id, tool: 'homelab.restartService', arguments: {service: 'vaultwarden'}, context: {sessionId: 'original', userRequest: 'Restart Vaultwarden'}, expiresAt: now + 600000, status};
  const gateway = async (method, path, data) => {
    if (path === '/approvals') return {requests: record.status === 'PENDING' ? [record] : []};
    if (method === 'GET') return structuredClone(record);
    if (path.endsWith('/execute')) {executions.push(path); record.status = 'DONE'; record.outcome = {success: true}; return record.outcome;}
    assert.equal(Object.hasOwn(data, 'id'), false);
    decisions.push(data); record.status = data.approve ? 'APPROVED' : 'REJECTED'; return {success: true};
  };
  const matrix = async (method, path, data) => {
    if (path.startsWith('/sync?')) return {next_batch: 'next', rooms: {join: {[room]: {timeline: {events, limited}}}}};
    if (method === 'GET') return encrypted ? [{type: 'm.room.encryption'}] : [];
    sends.push({path, data}); return {event_id: '$prompt'};
  };
  const relay = new ApprovalRelay({room, users: [user], state, matrix, gateway, save: () => {}, now: () => now, log: entry => logs.push(entry)});
  return {relay, state, sends, decisions, executions, logs, record, events: value => {events = value;}};
}

test('trusted prompt, verified event and exact stored execution form one approval lifecycle', async () => {
  const f = fixture(); await f.relay.tick(); assert.equal(f.sends.filter(item => item.path.includes('/send/m.room.message/')).length, 1);
  assert.ok(f.sends[0].data.body.includes('"service": "vaultwarden"'));
  f.events([event]); await f.relay.tick();
  assert.equal(f.decisions.length, 1); assert.equal(f.decisions[0].matrixEventId, '$decision');
  assert.equal(f.executions.length, 1); assert.equal(f.state.prompts[id].finished, true);
  await f.relay.tick(); assert.equal(f.executions.length, 1);
});

test('rejection never calls execution', async () => {
  const f = fixture(); await f.relay.tick();
  f.events([{...event, content: {...event.content, body: `!reject ${id}`}}]); await f.relay.tick();
  assert.equal(f.record.status, 'REJECTED'); assert.equal(f.executions.length, 0);
});

test('history gaps, bot messages and encrypted rooms cannot approve actions', async () => {
  const gap = fixture({limited: true}); await gap.relay.tick(); gap.events([event]); await gap.relay.tick(); assert.equal(gap.executions.length, 0);
  const bot = fixture(); await bot.relay.tick(); bot.events([{...event, sender: '@bot:server'}]); await bot.relay.tick(); assert.equal(bot.executions.length, 0);
  const encrypted = fixture({encrypted: true}); await encrypted.relay.tick(); assert.equal(encrypted.sends.length, 0);
  assert.equal(encrypted.logs[0].stage, 'prompt'); assert.equal(encrypted.executions.length, 0);
});

test('an ambiguous previous execution is reported rather than replayed after restart', async () => {
  const f = fixture({status: 'CONSUMED'});
  f.state.prompts[id] = {...prompts[id], decision: {approve: true}, executionAttempted: true};
  await f.relay.tick(); assert.equal(f.executions.length, 0); assert.ok(f.sends[0].data.body.includes('uncertain'));
});

test('completed workflow plans are delivered once without another write execution', async () => {
  const sends = [], state = {since:'initial',prompts:{[id]:{...prompts[id],finished:true,workflowPending:true}}};
  const relay = new ApprovalRelay({room,users:[user],state,save:()=>{},now:()=>now,
    matrix:async(method,path,data)=>{
      if(path.startsWith('/sync?'))return {next_batch:'next'};
      if(method==='GET')return [];
      if(path.startsWith('/_matrix/media/'))return {content_uri:'mxc://server/plan'};
      sends.push(data);return {event_id:'$plan'};
    },
    gateway:async(method,path)=>{
      assert.equal(method,'GET');
      if(path==='/approvals')return {requests:[]};
      assert.equal(path,`/approvals/${id}/workflow`);
      return {success:true,data:{status:'DONE',task_id:'test',run_id:'run',outputs:{'concept-plan.md':'Existing concept output','grounded-plan.md':'Existing grounded output'}}};
    },
  });
  await relay.tick();assert.equal(sends.length,3);assert.ok(sends[0].body.includes('Outcome: DONE'));
  assert.deepEqual(sends.slice(1).map(data=>data.filename),['concept-plan.md','grounded-plan.md']);
  await relay.tick();assert.equal(sends.length,3);
});

test('an unconfirmed run-start notice is retried before workflow delivery without replaying execution', async () => {
  const f = fixture({status: 'DONE'});
  f.record.tool = 'flowforge.run'; f.record.outcome = {data: {run_id: 'run'}};
  f.state.prompts[id] = {...prompts[id], decision: {approve: true}, executionAttempted: true};
  const matrix = f.relay.matrix;
  let fail = true;
  f.relay.matrix = async (...args) => {
    const result = await matrix(...args);
    if (args[1].endsWith(`approval-${id}-result`) && fail) throw new Error('response lost');
    return result;
  };
  await f.relay.tick();
  assert.equal(f.state.prompts[id].workflowPending, undefined);
  assert.equal(f.state.prompts[id].finished, undefined);
  const restarted = new ApprovalRelay({...f.relay, state: structuredClone(f.state)});
  fail = false; await restarted.tick();
  assert.equal(restarted.state.prompts[id].workflowPending, true);
  assert.equal(restarted.state.prompts[id].finished, true);
  assert.equal(f.executions.length, 0);
  assert.equal(f.sends.length, 2); assert.deepEqual(f.sends[0], f.sends[1]);
});

test('a failed workflow lookup does not block another workflow or approval and retries safely', async () => {
  const workflowId = '22345678-1234-1234-1234-123456789abc';
  const approvalId = '32345678-1234-1234-1234-123456789abc';
  const state = {since: 'initial', prompts: {
    [id]: {...prompts[id], finished: true, workflowPending: true},
    [workflowId]: {...prompts[id], finished: true, workflowPending: true},
    [approvalId]: {...prompts[id], decision: {approve: false}},
  }};
  const sends = [], logs = [], lookups = [];
  let fail = true;
  const relay = new ApprovalRelay({room, users: [user], state, save: () => {}, now: () => now, log: entry => logs.push(entry),
    matrix: async (method, path, data) => {
      if (path.startsWith('/sync?')) return {next_batch: 'next'};
      if (method === 'GET') return [];
      if (path.startsWith('/_matrix/media/')) return {content_uri: 'mxc://server/plan'};
      sends.push({path, data}); return {event_id: '$result'};
    },
    gateway: async (method, path) => {
      assert.equal(method, 'GET');
      if (path === '/approvals') return {requests: []};
      if (path === `/approvals/${approvalId}`) return {status: 'REJECTED'};
      lookups.push(path);
      if (path === `/approvals/${id}/workflow` && fail) {
        throw Object.assign(new Error('secret credential and full payload'), {code: 'secret credential'});
      }
      return {data: {status: 'DONE', task_id: 'task', run_id: path,
        outputs: {'concept-plan.md': 'Concept plan', 'grounded-plan.md': 'Grounded plan'}}};
    },
  });
  await relay.tick();
  assert.equal(state.prompts[id].workflowPending, true);
  assert.equal(state.prompts[workflowId].workflowPending, false);
  assert.equal(state.prompts[approvalId].finished, true);
  assert.equal(sends.length, 4);
  assert.deepEqual(logs, [{timestamp: new Date(now).toISOString(), event: 'approval_relay_operation_failed',
    code: 'APPROVAL_RELAY_OPERATION_FAILED', approvalId: id, stage: 'workflow_result'}]);
  fail = false;
  await relay.tick();
  assert.equal(state.prompts[id].workflowPending, false);
  assert.equal(sends.length, 7);
  assert.equal(lookups.filter(path => path === `/approvals/${workflowId}/workflow`).length, 1);
});

test('a failed prompt send does not block other prompts and retries the same Matrix transaction', async () => {
  const f = fixture(), otherId = '22345678-1234-1234-1234-123456789abc';
  const gateway = f.relay.gateway, matrix = f.relay.matrix, attempts = [];
  let fail = true;
  f.relay.gateway = (method, path, data) => path === '/approvals'
    ? {requests: [f.record, {...f.record, id: otherId}]} : gateway(method, path, data);
  f.relay.matrix = async (method, path, data) => {
    if (path.endsWith(`approval-${id}-prompt`)) {
      attempts.push(path);
      if (fail) throw new Error('ambiguous Matrix send');
    }
    return matrix(method, path, data);
  };
  await f.relay.tick();
  assert.equal(f.state.prompts[id].eventId, undefined);
  assert.equal(f.state.prompts[otherId].eventId, '$prompt');
  assert.equal(f.logs[0].approvalId, id); assert.equal(f.logs[0].stage, 'prompt');
  const sent = f.sends.length;
  fail = false;
  await f.relay.tick();
  assert.equal(f.state.prompts[id].eventId, '$prompt');
  assert.equal(f.sends.length, sent + 3);
  assert.equal(attempts.length, 2); assert.equal(attempts[0], attempts[1]);
});

test('a failed approval lookup allows other results and remains eligible for execution', async () => {
  const f = fixture(), otherId = '22345678-1234-1234-1234-123456789abc';
  await f.relay.tick(); f.events([event]);
  f.state.prompts[otherId] = {...prompts[id], decision: {approve: false}};
  const gateway = f.relay.gateway;
  let fail = true;
  f.relay.gateway = (method, path, data) => {
    if (path === `/approvals/${otherId}`) return {status: 'REJECTED'};
    if (path === `/approvals/${id}` && fail) throw new Error('transient status failure');
    return gateway(method, path, data);
  };
  await f.relay.tick();
  assert.equal(f.executions.length, 0);
  assert.equal(f.state.prompts[id].finished, undefined);
  assert.equal(f.state.prompts[otherId].finished, true);
  assert.equal(f.logs[0].stage, 'reconcile');
  fail = false;
  await f.relay.tick(); await f.relay.tick();
  assert.equal(f.executions.length, 1); assert.equal(f.state.prompts[id].finished, true);
});

test('an ambiguous execution failure is isolated and its durable claim prevents replay after restart', async () => {
  const f = fixture(), otherId = '22345678-1234-1234-1234-123456789abc';
  await f.relay.tick(); f.events([event]);
  f.state.prompts[otherId] = {...prompts[id], decision: {approve: false}};
  const gateway = f.relay.gateway;
  let saved;
  f.relay.save = state => {saved = structuredClone(state);};
  f.relay.gateway = (method, path, data) => {
    if (path === `/approvals/${otherId}`) return {status: 'REJECTED'};
    if (path.endsWith('/execute')) {
      assert.equal(saved.prompts[id].executionAttempted, true);
      f.executions.push(path); f.record.status = 'CONSUMED';
      throw new Error('execution response lost');
    }
    return gateway(method, path, data);
  };
  await f.relay.tick();
  assert.equal(f.state.prompts[otherId].finished, true);
  assert.equal(f.logs[0].stage, 'reconcile');
  const restarted = new ApprovalRelay({...f.relay, state: structuredClone(saved)});
  await restarted.tick(); await restarted.tick();
  assert.equal(f.executions.length, 1);
  assert.equal(restarted.state.prompts[id].finished, true);
  assert.ok(f.sends.some(item => item.data.body?.includes('uncertain')));
});

function reaction(key = '✅', target = '$prompt', sender = user) {
  return {type: 'm.reaction', sender, event_id: '$reaction', origin_server_ts: now,
    content: {'m.relates_to': {rel_type: 'm.annotation', event_id: target, key}}};
}

test('approval reactions bind the authorized user to the exact pending prompt', () => {
  const approve = decisionFor(reaction(), room, room, [user], prompts, now);
  assert.equal(approve?.approve, true);
  assert.equal(approve.promptEventId, '$prompt');
  assert.equal(approve.matrixEventId, '$reaction');
  assert.equal(decisionFor(reaction('❌'), room, room, [user], prompts, now)?.approve, false);
  for (const input of [reaction('👍'), reaction('✅', '$unrelated'), reaction('✅', '$prompt', '@bot:server'),
    {...reaction(), unsigned: {redacted_because: {}}},
    {...reaction(), origin_server_ts: now - 5000},
    {...reaction(), content: {'m.relates_to': {rel_type:'m.reference',event_id:'$prompt',key:'✅'}}},
  ]) assert.equal(decisionFor(input, room, room, [user], prompts, now), null);
  assert.equal(decisionFor(reaction(), '!elsewhere:server', room, [user], prompts, now), null);
  assert.equal(decisionFor(reaction(), room, room, [user], {[id]: {...prompts[id], expiresAt: now}}, now), null);
  assert.equal(decisionFor(reaction(), room, room, [user], {[id]: {...prompts[id], finished: true}}, now), null);
  assert.equal(decisionFor(reaction(), room, room, [user], {[id]: {...prompts[id], decision: {approve:false}}}, now), null);
});

test('bot-seeded reaction controls are idempotent and never approve their own prompt', async () => {
  const f = fixture(); await f.relay.tick();
  const controls = f.sends.filter(item => item.path.includes('/send/m.reaction/'));
  assert.deepEqual(controls.map(item => item.data['m.relates_to'].key), ['✅','❌']);
  assert.ok(controls.every(item => item.data['m.relates_to'].event_id === '$prompt'));
  f.events([reaction('✅', '$prompt', '@bot:server')]); await f.relay.tick();
  assert.equal(f.executions.length, 0);
  assert.equal(f.sends.filter(item => item.path.includes('/send/m.reaction/')).length, 2);
  f.events([reaction()]); await f.relay.tick();
  assert.equal(f.executions.length, 1);
  await f.relay.tick(); assert.equal(f.executions.length, 1);
});

test('reaction rejection never executes, including a later conflicting approval', async () => {
  const f = fixture(); await f.relay.tick();
  f.events([reaction('❌'),reaction('✅')]); await f.relay.tick();
  assert.equal(f.record.status,'REJECTED'); assert.equal(f.executions.length,0);
});

test('Matrix sync explicitly requests reaction events as well as text fallback commands', async () => {
  let filter;
  const relay = new ApprovalRelay({room,users:[user],state:{since:'cursor'},save:()=>{},gateway:()=>{},matrix:async (_method,path)=>{
    filter=JSON.parse(new URL(path,'http://matrix').searchParams.get('filter'));
    return {next_batch:'next'};
  }});
  await relay.sync();
  assert.deepEqual(filter.room.timeline.types,['m.room.message','m.reaction']);
});
