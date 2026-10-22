// Run inside the gateway container. The operator token never enters Hermes.
const [id, decision] = process.argv.slice(2);
if (id && (!/^[0-9a-f-]{36}$/.test(id) || !['approve', 'reject'].includes(decision))) {
  throw new Error('Usage: operator.mjs [APPROVAL_ID approve|reject]');
}
const response = await fetch(`http://127.0.0.1:8080/approvals${id ? `/${id}` : ''}`, {
  method: id ? 'POST' : 'GET',
  headers: {authorization: `Bearer ${process.env.APPROVER_TOKEN}`, 'content-type': 'application/json'},
  body: id ? JSON.stringify({approve: decision === 'approve', operator: process.env.OPERATOR || 'local-operator'}) : undefined,
});
console.log(JSON.stringify(await response.json(), null, 2));
if (!response.ok) process.exitCode = 1;
