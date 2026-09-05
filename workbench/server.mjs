import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { createHash, randomBytes } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { metadata, catalog, mapTasks, validateProject, InputError, requireValue } from './core.mjs';
import { createStore } from './store.mjs';

const PREFIX = '/workbench';
const assets = new Map([['/', ['index.html', 'text/html']], ['/app.js', ['app.js', 'text/javascript']],
  ['/style.css', ['style.css', 'text/css']],
  ['/example.html', ['example.html', 'text/html']], ['/example.js', ['example.js', 'text/javascript']],
  ['/example.css', ['example.css', 'text/css']], ['/dissolving-example.json', ['dissolving-example.json', 'application/json']], ['/integration.html', ['integration.html', 'text/html']]]);
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
async function readBody(req) {
  let size = 0, data = '';
  for await (const chunk of req) {
    size += chunk.length;
    requireValue(size <= 128 * 1024, '输入超过 128 KB，请减少任务或候选数量', 413);
    data += chunk;
  }
  try { return JSON.parse(data); } catch { throw new InputError('请输入有效的 JSON'); }
}
export async function startServer({ port = Number(process.env.PORT ?? 3412), host = '127.0.0.1', store, origin = process.env.WORKBENCH_ORIGIN, secure = process.env.NODE_ENV === 'production' } = {}) {
  store ??= await createStore();
  const buckets = new Map();
  let activeMaps = 0;
  function throttle(ip) {
    const minute = Math.floor(Date.now() / 60000);
    if (buckets.size > 5000) for (const [key, val] of buckets) if (val.minute !== minute) buckets.delete(key);
    const b = buckets.get(ip) ?? { minute, count: 0 };
    if (b.minute !== minute) { b.minute = minute; b.count = 0; }
    b.count++; buckets.set(ip, b);
    requireValue(b.count <= 20, '本分钟操作较多，请稍后再试', 429);
  }
  const server = createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'same-origin');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
    const json = (status, value) => { res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify(value)); };
    try {
      const url = new URL(req.url, 'http://localhost');
      if (url.pathname === PREFIX) { res.writeHead(302, { Location: `${PREFIX}/` }); return res.end(); }
      requireValue(url.pathname.startsWith(`${PREFIX}/`), '未找到页面', 404);
      const path = url.pathname.slice(PREFIX.length);
      if (req.method === 'GET' && assets.has(path)) {
        const [file, mime] = assets.get(path);
        res.writeHead(200, { 'Content-Type': `${mime}; charset=utf-8` });
        return res.end(await readFile(new URL(`public/${file}`, import.meta.url)));
      }
      requireValue(path.startsWith('/api/'), '未找到接口', 404);
      requireValue(['GET', 'POST'].includes(req.method), '不支持此请求方法', 405);
      const expectedOrigin = origin ?? `http://${req.headers.host}`;
      if (req.headers.origin) requireValue(req.headers.origin === expectedOrigin, '请从工作台页面发起此操作', 403);
      if (req.method === 'GET' && path === '/api/health') return json(200, { ok: true, database: await store.health(), datasetVersion: metadata().datasetVersion });
      if (req.method === 'GET' && path === '/api/meta') return json(200, metadata());
      if (req.method === 'GET' && path === '/api/catalog') return json(200, catalog({ grade: Number(url.searchParams.get('grade') ?? 3),
        query: url.searchParams.get('q') ?? '', offset: Number(url.searchParams.get('offset') ?? 0), limit: Number(url.searchParams.get('limit') ?? 30) }));
      if (req.method === 'POST') {
        requireValue(req.headers['content-type']?.split(';')[0] === 'application/json', '请使用 application/json', 415);
        throttle(req.headers['x-real-ip'] ?? req.socket.remoteAddress);
      }
      if (req.method === 'POST' && path === '/api/map') {
        requireValue(activeMaps < 2, '当前正在处理其他映射，请稍后再试', 503);
        const body = await readBody(req);
        activeMaps++;
        try { return json(200, await mapTasks(body)); } finally { activeMaps--; }
      }
      if (req.method === 'POST' && path === '/api/validate') return json(200, validateProject(await readBody(req)));
      requireValue(path === '/api/projects' || /^\/api\/projects\/[a-f0-9-]+$/.test(path), '未找到接口', 404);
      // The opaque HttpOnly cookie isolates anonymous workspaces. It is never an expert identity.
      let token = req.headers.cookie?.split(';').map(s => s.trim()).find(s => s.startsWith('k12_workspace='))?.slice(14);
      if (!token || !/^[a-f0-9]{64}$/.test(token)) {
        token = randomBytes(32).toString('hex');
        res.setHeader('Set-Cookie', `k12_workspace=${token}; Path=/workbench; HttpOnly; SameSite=Strict; Max-Age=15552000${secure ? '; Secure' : ''}`);
      }
      const owner = createHash('sha256').update(token).digest('hex');
      if (req.method === 'GET') {
        if (path === '/api/projects') return json(200, { items: await store.list(owner) });
        const id = path.split('/').at(-1);
        requireValue(uuid.test(id), '项目编号无效');
        return json(200, await store.get(owner, id));
      }
      requireValue(path === '/api/projects', '未找到接口', 404);
      requireValue(req.headers.origin === expectedOrigin, '保存需要来自同源工作台会话', 403);
      const body = await readBody(req);
      requireValue(body && typeof body === 'object', '项目格式不正确');
      if (body.id) requireValue(uuid.test(body.id) && Number.isInteger(body.revision) && body.revision >= 1, '项目编号或修订号无效');
      const project = validateProject(body.project);
      return json(200, { ...await store.save(owner, project, body.id, body.revision), project });
    } catch (error) {
      if (!res.headersSent && !res.destroyed) json(error instanceof InputError ? error.status : 500,
        { error: error instanceof InputError ? error.message : '服务暂不可用，请稍后重试' });
      if (!(error instanceof InputError)) console.error('workbench request failed:', error.name);
    }
  });
  server.requestTimeout = 20000;
  server.headersTimeout = 10000;
  await new Promise((done, fail) => { server.once('error', fail); server.listen(port, host, done); });
  return { server, store, url: `http://${host}:${server.address().port}${PREFIX}`, async close() {
    await new Promise(done => { server.close(done); server.closeIdleConnections(); }); await store.close();
  } };
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const app = await startServer();
  console.log(`K12 workbench: ${app.url}/`);
  for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, async () => { await app.close(); process.exit(0); });
}
