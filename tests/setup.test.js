import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { SetupController } from '../src/setup.js';

delete process.env.DSH_PDF_DATA_DIR;
delete process.env.DSH_PDF_RUNTIME_DIR;

function tempDir(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pdf-setup-test-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

function fakeChild() {
  const child = new EventEmitter();
  child.pid = 4242;
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.killed = false;
  child.kill = () => { child.killed = true; };
  return child;
}

function make(t, overrides = {}) {
  const dir = overrides.dir || tempDir(t);
  const child = overrides.child || fakeChild();
  const spawnCalls = [];
  const spawnProcess = (command, args, options) => {
    spawnCalls.push({ command, args, options });
    return overrides.spawnResult ? overrides.spawnResult(command, args) : child;
  };
  const configPath = path.join(dir, 'config.json');
  const scriptPath = path.join(dir, 'setup.ps1');
  if (!fs.existsSync(scriptPath)) fs.writeFileSync(scriptPath, '# test');
  // CI installs a legacy .venv/runtime inside the package checkout; pin both to
  // the temporary data directory so this test stays isolated from it.
  const previousRuntime = process.env.DSH_PDF_RUNTIME_DIR;
  process.env.DSH_PDF_RUNTIME_DIR = path.join(dir, 'runtime');
  t.after(() => {
    if (previousRuntime === undefined) delete process.env.DSH_PDF_RUNTIME_DIR;
    else process.env.DSH_PDF_RUNTIME_DIR = previousRuntime;
  });
  const config = { pythonPath: path.join(dir, '.venv', 'Scripts', 'python.exe') };
  const controller = new SetupController(config, {
    dataDir: dir,
    configPath,
    scriptPath,
    platform: 'win32',
    powershellPath: 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe',
    spawnProcess,
    timeoutMs: 60000,
    ...overrides.options,
  });
  return { dir, configPath, scriptPath, controller, child, spawnCalls };
}

function makeReady(dir) {
  fs.mkdirSync(path.join(dir, '.venv', 'Scripts'), { recursive: true });
  fs.writeFileSync(path.join(dir, '.venv', 'Scripts', 'python.exe'), '');
  fs.mkdirSync(path.join(dir, 'runtime', 'tectonic'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'runtime', 'tectonic', 'tectonic.exe'), '');
  fs.mkdirSync(path.join(dir, 'runtime', 'pandoc', 'pandoc-3'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'runtime', 'pandoc', 'pandoc-3', 'pandoc.exe'), '');
  fs.writeFileSync(path.join(dir, 'config.json'), JSON.stringify({
    base_url: 'https://api.example.com/v1', model: 'vision-model', api_key: 'secret-key',
  }));
}

test('setup snapshot reports missing pieces and becomes ready', (t) => {
  const { dir, controller } = make(t);
  const empty = controller.snapshot();
  assert.equal(empty.ready, false);
  assert.equal(empty.platformOk, true);
  assert.deepEqual(empty.missing, { python: true, runtime: true, config: true, model: true });
  assert.equal(empty.running, false);

  makeReady(dir);
  const ready = controller.snapshot();
  assert.equal(ready.ready, true);
  assert.deepEqual(ready.missing, { python: false, runtime: false, config: false, model: false });
  assert.deepEqual(ready.config, { baseUrl: 'https://api.example.com/v1', model: 'vision-model', hasApiKey: true });
});

test('placeholder model and empty key are not treated as configured', (t) => {
  const { dir, controller } = make(t);
  fs.writeFileSync(path.join(dir, 'config.json'), JSON.stringify({
    base_url: 'https://api.example.com/v1', model: 'REPLACE_WITH_YOUR_VISION_MODEL', api_key: '',
  }));
  const snapshot = controller.snapshot();
  assert.equal(snapshot.ready, false);
  assert.equal(snapshot.missing.model, true);
  assert.equal(snapshot.configError, '');
});

test('start spawns the absolute PowerShell setup script and follows phases', (t) => {
  const { dir, scriptPath, controller, child, spawnCalls } = make(t);
  const started = controller.start();
  assert.equal(started.running, true);
  assert.equal(spawnCalls.length, 1);
  assert.equal(spawnCalls[0].command, 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe');
  assert.deepEqual(spawnCalls[0].args.slice(0, 6),
    ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', scriptPath, '-DataDir']);
  assert.equal(spawnCalls[0].args[6], path.resolve(dir));

  child.stdout.write('Creating Python environment with C:\\python\\python.exe ...\n');
  assert.equal(controller.snapshot().phase, 'python');
  child.stdout.write('Installing Python dependencies ...\n');
  assert.equal(controller.snapshot().phase, 'dependencies');
  child.stderr.write('Downloading tectonic ...\n');
  child.stderr.write('Downloading pandoc ...\n');
  child.stdout.write('PDF translator environment is ready.\n');
  assert.equal(controller.snapshot().phase, 'done');

  child.emit('close', 0);
  const finished = controller.snapshot();
  assert.equal(finished.running, false);
  assert.equal(finished.phase, 'done');
  assert.ok(finished.log.length > 0);
});

test('failed setup keeps the last useful log lines', (t) => {
  const { controller, child } = make(t);
  controller.start();
  child.stderr.write('Failed to download or extract tectonic: network unreachable\n');
  child.emit('close', 1);
  const snapshot = controller.snapshot();
  assert.equal(snapshot.running, false);
  assert.equal(snapshot.phase, 'failed');
  assert.match(snapshot.error, /network unreachable/);
});

test('cancel kills the process tree and ends as cancelled', (t) => {
  const { controller, child, spawnCalls } = make(t);
  controller.start();
  controller.cancel();
  const killer = spawnCalls.find((call) => call.command === 'taskkill');
  assert.ok(killer);
  assert.deepEqual(killer.args, ['/pid', '4242', '/T', '/F']);
  assert.equal(controller.snapshot().running, true);
  child.emit('close', 1);
  const snapshot = controller.snapshot();
  assert.equal(snapshot.running, false);
  assert.equal(snapshot.phase, 'cancelled');
});

test('starting twice does not spawn a second setup process', (t) => {
  const { controller, spawnCalls } = make(t);
  controller.start();
  controller.start();
  assert.equal(spawnCalls.filter((call) => call.args.includes('-DataDir')).length, 1);
});

test('saveConfig keeps unknown fields and the existing key, and never exposes it', (t) => {
  const { dir, controller } = make(t);
  fs.writeFileSync(path.join(dir, 'config.json'), JSON.stringify({
    base_url: 'https://old.example.com', model: 'old', api_key: 'keep-me', thinking: 'on', auto_repair_rounds: 5,
  }));
  const result = controller.saveConfig({ baseUrl: 'https://new.example.com/v1', model: 'vision-model' });
  assert.deepEqual(result, { baseUrl: 'https://new.example.com/v1', model: 'vision-model', hasApiKey: true, configError: '' });
  const saved = JSON.parse(fs.readFileSync(path.join(dir, 'config.json'), 'utf8'));
  assert.equal(saved.api_key, 'keep-me');
  assert.equal(saved.thinking, 'on');
  assert.equal(saved.auto_repair_rounds, 5);
  assert.equal(Object.values(result).includes('keep-me'), false);
});

test('saveConfig validates input and refuses to overwrite a broken file', (t) => {
  const { dir, controller } = make(t);
  assert.throws(() => controller.saveConfig({ baseUrl: 'ftp://example.com', model: 'x', apiKey: 'k' }), /http/);
  assert.throws(() => controller.saveConfig({ baseUrl: 'https://example.com/v1', model: ' ', apiKey: 'k' }), /模型名称/);
  assert.throws(() => controller.saveConfig({ baseUrl: 'https://example.com/v1', model: 'REPLACE_WITH_YOUR_VISION_MODEL', apiKey: 'k' }), /真实模型/);
  assert.throws(() => controller.saveConfig({ baseUrl: 'https://example.com/v1', model: 'vision' }), /API 密钥/);

  fs.writeFileSync(path.join(dir, 'config.json'), '{broken');
  const broken = controller.snapshot();
  assert.match(broken.configError, /config\.json/);
  assert.throws(() => controller.saveConfig({ baseUrl: 'https://example.com/v1', model: 'vision', apiKey: 'k' }), /config\.json/);
  assert.equal(fs.readFileSync(path.join(dir, 'config.json'), 'utf8'), '{broken');
});

test('unsupported platform refuses to install', (t) => {
  const { controller } = make(t, { options: { platform: 'linux' } });
  const snapshot = controller.start();
  assert.equal(snapshot.phase, 'failed');
  assert.match(snapshot.error, /Windows/);
});
