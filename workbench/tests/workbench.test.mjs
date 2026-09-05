import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { catalog, metadata, mapTasks, validateProject, validateInput, getCapability } from '../core.mjs';
import { createStore } from '../store.mjs';
import { startServer } from '../server.mjs';

const input = { title: '溶解实验室', grade: 3, tasks: [{ id: 'experiment', text: '通过对比实验，说明搅拌对食盐在水中溶解快慢的影响。' }] };
const clone = value => JSON.parse(JSON.stringify(value));

test('005: scientific scope excludes deprecated, non-citable and cross-secondary records', () => {
  assert.ok(metadata().count > 0);
  for (let grade = 1; grade <= 6; grade++) {
    const page = catalog({ grade, limit: 100 });
    for (const a of page.items) {
      assert.equal(a.discipline, '科学'); assert.equal(a.citable, true); assert.equal(a.deprecated, null);
      assert.ok(Number(a.stage.min.slice(1)) <= grade && Number(a.stage.max.slice(1)) >= grade);
      assert.ok(Number(a.stage.max.slice(1)) <= 6); assert.ok(a.provenance); assert.ok('warning' in a.grain);
    }
  }
  assert.throws(() => getCapability('ca_EGpSQPS4')); // G1–G9 specific heat must not enter a primary pilot.
  const first = catalog({ grade: 3, limit: 2 });
  const next = catalog({ grade: 3, limit: 2, offset: first.nextOffset });
  assert.equal(first.items.length, 2); assert.notEqual(first.items[0].id, next.items[0].id);
});

test('005: batch recall retains task boundary, provenance and pending-only decisions', async () => {
  const project = await mapTasks({ ...input, tasks: [...input.tasks, { id: 'none', text: 'abcdefghijklmnop' }] });
  assert.ok(project.tasks[0].candidates.some(c => c.anchor.id === 'ca_VKU9hc8E'));
  assert.equal(project.tasks[1].candidates.length, 0);
  for (const c of project.tasks[0].candidates) {
    assert.equal(c.status, 'pending'); assert.equal(c.relation, null);
    assert.ok(c.terms.every(term => input.tasks[0].text.includes(term) && c.anchor.statement.includes(term)));
    assert.ok(c.anchor.provenance.page); assert.equal('confidence' in c, false);
  }
});

test('005: inputs fail closed at boundaries', async () => {
  for (const patch of [{ grade: 7 }, { grade: 2.5 }, { title: '' }, { limit: -1 }, { limit: '6' }, { tasks: [] },
    { tasks: [{ text: 'a'.repeat(401) }] }, { tasks: Array(9).fill({ text: '观察植物生长' }) },
    { tasks: [{ id: 'x', text: '观察植物生长' }, { id: 'x', text: '观察植物生长' }] }]) {
    assert.throws(() => validateInput({ ...input, ...patch }));
  }
  assert.throws(() => validateInput(null));
});

test('005: confirmation requires original excerpt, relation and reason; canonical source cannot be forged', async () => {
  const project = await mapTasks(input);
  const c = project.tasks[0].candidates[0];
  c.status = 'confirmed';
  assert.throws(() => validateProject(project));
  c.relation = 'trains'; c.note = '任务要求改变搅拌条件并比较溶解快慢。';
  c.excerpt = '这是任务中不存在的句子'; assert.throws(() => validateProject(project));
  c.excerpt = input.tasks[0].text;
  c.anchor.provenance.text = '伪造的出处'; c.anchor.verifiedBy = 'human';
  const saved = validateProject(project);
  assert.notEqual(saved.tasks[0].candidates[0].anchor.provenance.text, '伪造的出处');
  assert.notEqual(saved.tasks[0].candidates[0].anchor.verifiedBy, 'human');
  const old = clone(saved); old.datasetFingerprint = 'old'; assert.throws(() => validateProject(old), /版本/);
  const duplicate = clone(saved); duplicate.tasks[0].candidates.push(duplicate.tasks[0].candidates[0]); assert.throws(() => validateProject(duplicate), /重复/);
  const fake = clone(saved); fake.tasks[0].candidates[0].anchor.id = 'ca_DOES_NOT_EXIST'; assert.throws(() => validateProject(fake));
});

test('005: persistence survives restart; owner isolation and optimistic revision checks', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'k12-workbench-'));
  const filename = join(dir, 'db.sqlite');
  let store;
  try {
    const p = await mapTasks(input);
    store = await createStore({ filename });
    const saved = await store.save('owner-a', p);
    assert.equal(saved.revision, 1);
    assert.equal((await store.list('owner-b')).length, 0);
    await assert.rejects(() => store.get('owner-b', saved.id), /没有找到/);
    await assert.rejects(() => store.save('owner-b', p, saved.id, 1), /其他窗口/);
    const updated = await store.save('owner-a', p, saved.id, 1); assert.equal(updated.revision, 2);
    await assert.rejects(() => store.save('owner-a', p, saved.id, 1), /其他窗口/);
    await store.close(); store = await createStore({ filename });
    assert.equal((await store.get('owner-a', saved.id)).revision, 2);
  } finally { await store?.close(); await rm(dir, { recursive: true, force: true }); }
});

test('005: actual HTTP mapping / import validation / session ownership / CSRF / errors', async () => {
  const store = await createStore({ filename: ':memory:' });
  const app = await startServer({ port: 0, store });
  const origin = new URL(app.url).origin;
  try {
    const get = path => fetch(`${app.url}/api/${path}`);
    const post = (path, body, headers = {}) => fetch(`${app.url}/api/${path}`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', Origin: origin, ...headers }, body: JSON.stringify(body) });
    assert.equal((await get('health')).status, 200);
    const page = await fetch(`${app.url}/`); assert.equal(page.status, 200); assert.match(await page.text(), /应用映射工作台/);
    const mapped = await post('map', input); assert.equal(mapped.status, 200); const project = await mapped.json();
    const session = await get('projects'), cookie = session.headers.get('set-cookie').split(';')[0];
    assert.match(session.headers.get('set-cookie'), /HttpOnly/);
    const saved = await post('projects', { project }, { Cookie: cookie }); assert.equal(saved.status, 200);
    const data = await saved.json();
    assert.equal((await get(`projects/${data.id}`)).status, 404);
    const own = await fetch(`${app.url}/api/projects/${data.id}`, { headers: { Cookie: cookie } });
    assert.equal((await own.json()).project.title, input.title);
    assert.equal((await post('projects', { project }, { Cookie: cookie, Origin: 'https://untrusted.invalid' })).status, 403);
    assert.equal((await post('projects', { project }, { Cookie: cookie, Origin: '' })).status, 403);
    assert.equal((await post('validate', project)).status, 200);
    assert.equal((await post('map', { ...input, grade: 9 })).status, 400);
    assert.equal((await post('map', { ...input, title: 'x'.repeat(140000) })).status, 413);
    assert.equal((await fetch(`${app.url}/api/map`, { method: 'POST', body: '{}' })).status, 415);
    assert.equal((await get('catalog?grade=Infinity')).status, 400);
    assert.equal((await get('projects/not-an-id')).status, 404);
  } finally { await app.close(); }
});

test('005: MCP handshake, structured result, invalid input and unchanged curriculum bytes', { timeout: 30000 }, async () => {
  const source = new URL('../../anchors/science.jsonl', import.meta.url);
  const digest = async () => createHash('sha256').update(await readFile(source)).digest('hex');
  const before = await digest();
  const child = spawn(process.execPath, [fileURLToPath(new URL('../../mcp/server.mjs', import.meta.url))],
    { env: { ...process.env, K12_USAGE: '0' }, stdio: ['pipe', 'pipe', 'pipe'] });
  const waiting = new Map(); let buffer = '', seq = 0;
  child.stderr.resume();
  child.stdout.on('data', data => {
    buffer += data;
    while (buffer.includes('\n')) {
      const i = buffer.indexOf('\n'), line = buffer.slice(0, i); buffer = buffer.slice(i + 1);
      const message = JSON.parse(line); waiting.get(message.id)?.(message); waiting.delete(message.id);
    }
  });
  const rpc = (method, params = {}) => new Promise(resolve => {
    const id = ++seq; waiting.set(id, resolve); child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  });
  try {
    const initialized = await rpc('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'workbench-test', version: '1' } });
    assert.equal(initialized.result.serverInfo.name, 'k12-substrate');
    const listing = await rpc('tools/list');
    const tool = listing.result.tools.find(t => t.name === 'map_science_tasks');
    assert.equal(tool.annotations.readOnlyHint, true);
    const mapped = await rpc('tools/call', { name: tool.name, arguments: input });
    assert.equal(mapped.result.isError, false);
    assert.deepEqual(mapped.result.structuredContent, JSON.parse(mapped.result.content[0].text));
    assert.ok(mapped.result.structuredContent.tasks[0].candidates.length);
    const bad = await rpc('tools/call', { name: tool.name, arguments: { ...input, grade: 12 } });
    assert.equal(bad.result.isError, true);
    assert.equal(await digest(), before);
  } finally { child.kill(); }
});
