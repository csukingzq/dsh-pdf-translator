import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {
  resolveDataDir,
  resolveConfigPath,
  resolvePythonPath,
  resolveRuntimeDir,
} from '../src/paths.js';

async function temp(t) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'dsh-pdf-paths-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  return dir;
}

test('data directory defaults to DSH_HOME and preserves legacy package state', async (t) => {
  const dir = await temp(t);
  const pluginRoot = path.join(dir, 'plugin');
  const home = path.join(dir, 'home');
  await fs.mkdir(pluginRoot, { recursive: true });
  const env = { DSH_HOME: home };
  assert.equal(resolveDataDir({}, { pluginRoot, env }), path.join(home, 'dsh-pdf-translator'));

  await fs.writeFile(path.join(pluginRoot, 'config.json'), '{}');
  assert.equal(resolveDataDir({}, { pluginRoot, env }), pluginRoot);
  assert.equal(resolveDataDir({ dataDir: path.join(dir, 'explicit') }, { pluginRoot, env }), path.join(dir, 'explicit'));
  assert.equal(resolveDataDir({}, { pluginRoot, env: { ...env, DSH_PDF_DATA_DIR: path.join(dir, 'env') } }), path.join(dir, 'env'));
});

test('config, Python and runtime resolve beside persistent data with legacy fallbacks', async (t) => {
  const dir = await temp(t);
  const pluginRoot = path.join(dir, 'plugin');
  const dataDir = path.join(dir, 'data');
  await fs.mkdir(pluginRoot, { recursive: true });
  await fs.mkdir(path.join(dataDir, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin'), { recursive: true });
  await fs.mkdir(path.join(dataDir, 'runtime'), { recursive: true });
  await fs.mkdir(path.join(pluginRoot, 'runtime'), { recursive: true });
  await fs.writeFile(path.join(pluginRoot, 'config.json'), '{"legacy":true}');
  await fs.writeFile(path.join(dataDir, 'config.json'), '{"persistent":true}');
  await fs.writeFile(path.join(dataDir, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'), '');
  const env = { DSH_HOME: path.join(dir, 'home') };

  assert.equal(resolveConfigPath({ dataDir }, dataDir, { pluginRoot, env }), path.join(dataDir, 'config.json'));
  assert.equal(resolvePythonPath({ dataDir }, dataDir, { pluginRoot, env }), path.join(dataDir, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'));
  assert.equal(resolveRuntimeDir({ dataDir }, dataDir, { pluginRoot, env }), path.join(dataDir, 'runtime'));

  const empty = path.join(dir, 'empty');
  await fs.mkdir(empty);
  assert.equal(resolveConfigPath({ dataDir: empty }, empty, { pluginRoot, env }), path.join(pluginRoot, 'config.json'));
  assert.equal(resolveRuntimeDir({ dataDir: empty }, empty, { pluginRoot, env }), path.join(pluginRoot, 'runtime'));
  assert.equal(resolvePythonPath({ pythonPath: 'C:/custom/python.exe' }, dataDir, { pluginRoot, env }), 'C:/custom/python.exe');
});
