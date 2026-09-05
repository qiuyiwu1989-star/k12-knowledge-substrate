// Application judgments live here, never in curriculum files. PostgreSQL in production.
import { randomUUID } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { InputError } from './core.mjs';

export async function createStore({ postgres = process.env.WORKBENCH_DB === 'postgres', filename = process.env.WORKBENCH_SQLITE ?? fileURLToPath(new URL('../var/workbench.sqlite', import.meta.url)) } = {}) {
  let query, close;
  if (postgres) {
    const { default: pg } = await import('pg');
    const pool = new pg.Pool({ max: 4, connectionTimeoutMillis: 5000, idleTimeoutMillis: 30000 });
    pool.on('error', () => console.error('workbench database connection unavailable'));
    await pool.query(`CREATE TABLE IF NOT EXISTS mapping_projects (
      id TEXT PRIMARY KEY, owner_hash TEXT NOT NULL, title TEXT NOT NULL,
      revision INTEGER NOT NULL, snapshot TEXT NOT NULL, updated_at TEXT NOT NULL
    )`);
    await pool.query('CREATE INDEX IF NOT EXISTS mapping_projects_owner ON mapping_projects(owner_hash)');
    query = async (sql, params = []) => {
      let i = 0;
      const result = await pool.query(sql.replace(/\?/g, () => `$${++i}`), params);
      return { rows: result.rows, changes: result.rowCount };
    };
    close = () => pool.end();
  } else {
    if (filename !== ':memory:') mkdirSync(dirname(filename), { recursive: true });
    const { DatabaseSync } = await import('node:sqlite');
    const db = new DatabaseSync(filename);
    db.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;');
    db.exec(`CREATE TABLE IF NOT EXISTS mapping_projects (
      id TEXT PRIMARY KEY, owner_hash TEXT NOT NULL, title TEXT NOT NULL,
      revision INTEGER NOT NULL, snapshot TEXT NOT NULL, updated_at TEXT NOT NULL
    ); CREATE INDEX IF NOT EXISTS mapping_projects_owner ON mapping_projects(owner_hash);`);
    query = async (sql, params = []) => {
      const statement = db.prepare(sql);
      if (/^\s*SELECT/i.test(sql)) return { rows: statement.all(...params) };
      return statement.run(...params);
    };
    close = () => db.close();
  }
  return {
    async health() { await query('SELECT 1'); return postgres ? 'postgresql' : 'sqlite'; },
    async list(owner) {
      return (await query('SELECT id, title, revision, updated_at FROM mapping_projects WHERE owner_hash = ? ORDER BY updated_at DESC LIMIT 50', [owner])).rows;
    },
    async get(owner, id) {
      const row = (await query('SELECT id, revision, snapshot, updated_at FROM mapping_projects WHERE id = ? AND owner_hash = ?', [id, owner])).rows[0];
      if (!row) throw new InputError('没有找到这个会话中的项目', 404);
      return { id: row.id, revision: row.revision, updatedAt: row.updated_at, project: JSON.parse(row.snapshot) };
    },
    async save(owner, project, id, revision) {
      const updatedAt = new Date().toISOString();
      if (id) {
        const changed = await query('UPDATE mapping_projects SET title = ?, snapshot = ?, revision = revision + 1, updated_at = ? WHERE id = ? AND owner_hash = ? AND revision = ?',
          [project.title, JSON.stringify(project), updatedAt, id, owner, revision]);
        if (!Number(changed.changes)) throw new InputError('项目已在其他窗口更新，或不属于当前会话。请先重新载入；可导出当前修改留存。', 409);
      } else {
        const count = (await query('SELECT COUNT(*) AS n FROM mapping_projects WHERE owner_hash = ?', [owner])).rows[0].n;
        if (Number(count) >= 50) throw new InputError('当前会话已保存 50 个项目，请导出留存或更新已有项目', 429);
        id = randomUUID(); revision = 0;
        await query('INSERT INTO mapping_projects (id, owner_hash, title, revision, snapshot, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
          [id, owner, project.title, 1, JSON.stringify(project), updatedAt]);
      }
      return { id, revision: revision + 1, updatedAt };
    },
    close,
  };
}
