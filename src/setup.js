import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { root, resolveConfigPath, resolveDataDir, resolvePythonPath, resolveRuntimeDir } from './paths.js';

const PLACEHOLDER_MODEL = /^REPLACE/i;
const MAX_LOG_LINES = 200;
const MAX_LINE_LENGTH = 500;
const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000;
const DEFAULT_CONFIG = { thinking: 'auto', auto_repair_rounds: 3 };
const PHASE_TEXT = {
  starting: '正在启动环境安装…',
  python: '创建 Python 环境…',
  dependencies: '安装 Python 依赖…',
  tectonic: '下载 Tectonic…',
  pandoc: '下载 Pandoc…',
  done: '环境已就绪',
};
const PHASE_RULES = [
  [/Creating Python environment/i, 'python'],
  [/Installing Python dependencies/i, 'dependencies'],
  [/Downloading tectonic/i, 'tectonic'],
  [/Downloading pandoc/i, 'pandoc'],
  [/PDF translator environment is ready/i, 'done'],
];

const existsFile = (file) => {
  try { return fs.statSync(file).isFile(); } catch { return false; }
};

function defaultPowerShell() {
  const systemRoot = process.env.SystemRoot || 'C:\\Windows';
  const candidate = path.join(systemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
  return existsFile(candidate) ? candidate : '';
}

function findPandoc(runtimeDir) {
  const folder = path.join(runtimeDir, 'pandoc');
  let names = [];
  try { names = fs.readdirSync(folder); } catch { return ''; }
  for (const name of names) {
    const candidate = path.join(folder, name, 'pandoc.exe');
    if (existsFile(candidate)) return candidate;
    if (existsFile(path.join(folder, 'pandoc.exe'))) return path.join(folder, 'pandoc.exe');
  }
  const direct = path.join(folder, 'pandoc.exe');
  return existsFile(direct) ? direct : '';
}

function phaseFor(line) {
  for (const [pattern, phase] of PHASE_RULES) if (pattern.test(line)) return phase;
  return '';
}

export class SetupController {
  constructor(config = {}, options = {}) {
    this.config = config;
    this.platform = options.platform || process.platform;
    this.dataDir = path.resolve(options.dataDir || resolveDataDir(config));
    this.configPath = path.resolve(options.configPath || resolveConfigPath(config, this.dataDir));
    this.scriptPath = options.scriptPath || path.join(root, 'scripts', 'setup.ps1');
    this.spawn = options.spawnProcess || spawn;
    this.powershell = options.powershellPath === undefined ? defaultPowerShell() : options.powershellPath;
    this.now = options.now || Date.now;
    this.timeoutMs = options.timeoutMs || DEFAULT_TIMEOUT_MS;
    this.running = false;
    this.phase = 'idle';
    this.message = '';
    this.error = '';
    this.log = [];
    this.startedAt = 0;
    this.finishedAt = 0;
    this.child = null;
    this.cancelled = false;
    this.timer = null;
    this.timedOut = '';
  }

  readConfigFile() {
    if (!existsFile(this.configPath)) return { exists: false, error: '', value: null };
    try {
      const text = fs.readFileSync(this.configPath, 'utf8').replace(/^\uFEFF/, '').trim();
      if (!text) return { exists: false, error: '', value: null };
      const value = JSON.parse(text);
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('顶层必须是对象');
      return { exists: true, error: '', value };
    } catch (error) {
      return { exists: true, error: 'config.json 格式错误：' + error.message, value: null };
    }
  }

  configInfo() {
    const file = this.readConfigFile();
    const value = file.value || {};
    return {
      baseUrl: typeof value.base_url === 'string' ? value.base_url : '',
      model: typeof value.model === 'string' ? value.model : '',
      hasApiKey: Boolean(value.api_key),
      configError: file.error,
    };
  }

  saveConfig(input = {}) {
    const baseUrl = String(input.baseUrl || '').trim().replace(/\/+$/, '');
    if (!/^https?:\/\/[^\s/]+/i.test(baseUrl)) throw new Error('接口地址必须以 http:// 或 https:// 开头。');
    const model = String(input.model || '').trim();
    if (!model) throw new Error('请填写模型名称。');
    if (PLACEHOLDER_MODEL.test(model)) throw new Error('请把示例模型名替换成支持图片输入的真实模型。');
    const file = this.readConfigFile();
    if (file.error) throw new Error(file.error + ' 请修复或删除后重试。');
    const current = file.value || { ...DEFAULT_CONFIG };
    const next = { ...current, base_url: baseUrl, model };
    const apiKey = typeof input.apiKey === 'string' ? input.apiKey.trim() : '';
    if (apiKey) next.api_key = apiKey;
    if (!next.api_key) throw new Error('请填写 API 密钥。');
    fs.mkdirSync(path.dirname(this.configPath), { recursive: true });
    const temp = this.configPath + '.tmp';
    fs.writeFileSync(temp, JSON.stringify(next, null, 2) + '\n', 'utf8');
    fs.renameSync(temp, this.configPath);
    return this.configInfo();
  }

  snapshot() {
    const platformOk = this.platform === 'win32';
    const venvPython = path.join(this.dataDir, '.venv', 'Scripts', 'python.exe');
    const configuredPython = resolvePythonPath(this.config, this.dataDir);
    const python = existsFile(venvPython) || (path.isAbsolute(configuredPython) && existsFile(configuredPython));
    const runtimeDir = resolveRuntimeDir(this.config, this.dataDir);
    const runtime = existsFile(path.join(runtimeDir, 'tectonic', 'tectonic.exe')) && Boolean(findPandoc(runtimeDir));
    const file = this.readConfigFile();
    const value = file.value || {};
    const baseUrl = typeof value.base_url === 'string' ? value.base_url.trim() : '';
    const model = typeof value.model === 'string' ? value.model.trim() : '';
    const hasApiKey = Boolean(value.api_key);
    const modelReady = /^https?:\/\//i.test(baseUrl) && Boolean(model) && !PLACEHOLDER_MODEL.test(model) && hasApiKey;
    const missing = { python: !python, runtime: !runtime, config: !file.exists, model: !modelReady };
    return {
      platform: this.platform,
      platformOk,
      ready: platformOk && !missing.python && !missing.runtime && !missing.model,
      running: this.running,
      phase: this.phase,
      message: this.message,
      error: this.error,
      configError: file.error,
      elapsedSeconds: this.running && this.startedAt ? Math.max(0, Math.round((this.now() - this.startedAt) / 1000)) : 0,
      log: this.log.slice(-6),
      missing,
      config: {
        baseUrl,
        model,
        hasApiKey,
      },
    };
  }

  start() {
    if (this.platform !== 'win32') {
      this.phase = 'failed';
      this.error = '当前系统不支持自动安装，仅支持 Windows。';
      return this.snapshot();
    }
    if (this.running) return this.snapshot();
    if (!existsFile(this.scriptPath)) {
      this.phase = 'failed';
      this.error = '插件缺少 scripts/setup.ps1，请重新安装插件。';
      return this.snapshot();
    }
    if (!this.powershell) {
      this.phase = 'failed';
      this.error = '找不到 Windows PowerShell，请检查系统安装或手动运行 setup.ps1。';
      return this.snapshot();
    }
    this.running = true;
    this.cancelled = false;
    this.timedOut = '';
    this.phase = 'starting';
    this.message = PHASE_TEXT.starting;
    this.error = '';
    this.log = [];
    this.startedAt = this.now();
    this.finishedAt = 0;
    let child;
    try {
      child = this.spawn(this.powershell,
        ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', this.scriptPath, '-DataDir', this.dataDir],
        { cwd: root, windowsHide: true, shell: false, stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (error) {
      this.fail('无法启动 PowerShell：' + error.message);
      return this.snapshot();
    }
    this.child = child;
    for (const stream of [child.stdout, child.stderr]) {
      if (!stream || typeof stream.setEncoding !== 'function') continue;
      stream.setEncoding('utf8');
      let buffer = '';
      stream.on('data', (chunk) => {
        buffer += chunk;
        let index;
        while ((index = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, index).replace(/\r$/, '').trim();
          buffer = buffer.slice(index + 1);
          if (line) this.push(line);
        }
      });
    }
    child.on('error', (error) => this.fail('无法启动 PowerShell：' + error.message));
    child.on('close', (code) => this.finish(code));
    this.timer = setTimeout(() => {
      this.timedOut = '环境准备超时，请检查网络后重试。';
      this.cancel();
    }, this.timeoutMs);
    this.timer.unref?.();
    return this.snapshot();
  }

  cancel() {
    if (!this.running) return this.snapshot();
    this.cancelled = true;
    this.message = '正在取消…';
    const child = this.child;
    if (child?.pid && this.platform === 'win32') {
      try {
        const killer = this.spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
        killer?.on?.('error', () => child.kill?.());
        killer?.unref?.();
      } catch {
        child.kill?.();
      }
    } else {
      child?.kill?.();
    }
    return this.snapshot();
  }

  push(line) {
    this.log.push(line.slice(0, MAX_LINE_LENGTH));
    if (this.log.length > MAX_LOG_LINES) this.log.splice(0, this.log.length - MAX_LOG_LINES);
    const phase = phaseFor(line);
    if (phase) {
      this.phase = phase;
      this.message = PHASE_TEXT[phase] || line;
    } else if (this.phase === 'starting') {
      this.message = line.slice(0, 200);
    }
  }

  fail(message) {
    if (!this.running) return;
    this.running = false;
    this.child = null;
    this.phase = 'failed';
    this.error = message;
    this.message = message;
    this.finishedAt = this.now();
    this.clearTimer();
  }

  finish(code) {
    if (!this.running) return;
    this.running = false;
    this.child = null;
    this.finishedAt = this.now();
    this.clearTimer();
    if (this.timedOut) {
      this.phase = 'failed';
      this.error = this.timedOut;
      this.message = this.timedOut;
    } else if (this.cancelled) {
      this.phase = 'cancelled';
      this.message = '已取消环境准备。';
    } else if (code === 0) {
      this.phase = 'done';
      this.message = PHASE_TEXT.done;
    } else {
      const tail = this.log.filter(Boolean).slice(-3).join(' ');
      this.phase = 'failed';
      this.error = tail
        ? '环境准备失败：' + tail
        : `环境准备失败（退出码 ${code}）。请检查网络后重试。`;
      this.message = this.error;
    }
  }

  clearTimer() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }
}

export const setupPhaseText = PHASE_TEXT;
