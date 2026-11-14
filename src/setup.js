import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { root, resolveConfigPath, resolveDataDir, resolvePythonPath, resolveRuntimeDir } from './paths.js';

const PLACEHOLDER_MODEL = /^REPLACE/i;
const MAX_LOG_LINES = 200;
const MAX_LINE_LENGTH = 500;
const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000;
const PROBE_TIMEOUT_MS = 20000;
const DEFAULT_CONFIG = {};
const PHASE_TEXT = {
  starting: '正在启动环境安装…',
  python: '创建 Python 环境…',
  dependencies: '安装 Python 依赖…',
  engine: '安装翻译引擎（pdf2zh-next）…',
  done: '环境已就绪',
};
const PHASE_RULES = [
  [/Creating Python environment/i, 'python'],
  [/Installing Python dependencies/i, 'dependencies'],
  [/Installing the translation engine/i, 'engine'],
  [/PDF translator environment is ready/i, 'done'],
];
const PROBE_CODE = "import importlib.metadata as m; print(m.version('pdf2zh-next'))";

const existsFile = (file) => {
  try { return fs.statSync(file).isFile(); } catch { return false; }
};

function defaultPowerShell() {
  const systemRoot = process.env.SystemRoot || 'C:\\Windows';
  const candidate = path.join(systemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
  return existsFile(candidate) ? candidate : '';
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
    this.runtimeDir = path.resolve(options.runtimeDir || resolveRuntimeDir(config, this.dataDir));
    this.scriptPath = options.scriptPath || path.join(root, 'scripts', 'setup.ps1');
    this.spawn = options.spawnProcess || spawn;
    this.powershell = options.powershellPath === undefined ? defaultPowerShell() : options.powershellPath;
    this.now = options.now || Date.now;
    this.timeoutMs = options.timeoutMs || DEFAULT_TIMEOUT_MS;
    this.allowProbe = options.probe !== false;
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
    this.engine = { ready: false, version: '', error: '', probed: false };
    this.probed = null;
  }

  markerPath() {
    return path.join(this.runtimeDir, 'pdf2zh.json');
  }

  marker() {
    try {
      // Windows PowerShell 5.1 writes -Encoding utf8 with a BOM.
      const text = fs.readFileSync(this.markerPath(), 'utf8').replace(/^\uFEFF/, '');
      const value = JSON.parse(text);
      return { version: typeof value.version === 'string' ? value.version : '' };
    } catch {
      return { version: '' };
    }
  }

  pythonPath() {
    return resolvePythonPath(this.config, this.dataDir);
  }

  hasPython() {
    const venvPython = path.join(this.dataDir, '.venv', 'Scripts', 'python.exe');
    const configured = this.pythonPath();
    return existsFile(venvPython) || (path.isAbsolute(configured) && existsFile(configured));
  }

  // Cheap readiness probe: the setup script's marker first, then one spawn of
  // the configured interpreter so an existing engine environment works too.
  prime() {
    if (this.probed) return this.probed;
    this.probed = this.probe().catch(() => {}).finally(() => { this.probed = null; });
    return this.probed;
  }

  async probe() {
    const marker = this.marker();
    if (marker.version) {
      this.engine = { ready: true, version: marker.version, error: '', probed: true };
      return this.engine;
    }
    if (!this.allowProbe) {
      this.engine = { ready: false, version: '', error: '', probed: false };
      return this.engine;
    }
    const python = this.pythonPath();
    if (path.isAbsolute(python) && !existsFile(python)) {
      this.engine = { ready: false, version: '', error: 'Python 环境不存在：' + python, probed: true };
      return this.engine;
    }
    let result;
    try {
      result = await this.exec(python, ['-c', PROBE_CODE]);
    } catch (error) {
      this.engine = { ready: false, version: '', error: '无法运行 Python：' + error.message, probed: true };
      return this.engine;
    }
    const version = String(result.out || '').trim().split('\n').pop().trim();
    if (result.code === 0 && /^\d+\.\d+/.test(version)) {
      this.engine = { ready: true, version, error: '', probed: true };
    } else {
      this.engine = { ready: false, version: '', error: '未安装 pdf2zh-next 翻译引擎。', probed: true };
    }
    return this.engine;
  }

  exec(command, args) {
    return new Promise((resolve) => {
      let child;
      try {
        child = this.spawn(command, args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
      } catch (error) {
        resolve({ code: -1, out: '', err: error.message });
        return;
      }
      let out = '', err = '';
      const timer = setTimeout(() => { try { child.kill?.(); } catch {} }, PROBE_TIMEOUT_MS);
      timer.unref?.();
      child.stdout?.setEncoding?.('utf8');
      child.stderr?.setEncoding?.('utf8');
      child.stdout?.on?.('data', (chunk) => { out += chunk; });
      child.stderr?.on?.('data', (chunk) => { err += chunk; });
      child.on?.('error', (error) => { clearTimeout(timer); resolve({ code: -1, out, err: error.message }); });
      child.on?.('close', (code) => { clearTimeout(timer); resolve({ code: code === null ? -1 : code, out, err }); });
    });
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
    if (PLACEHOLDER_MODEL.test(model)) throw new Error('请把示例模型名替换成真实的模型。');
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
    const python = this.hasPython();
    // The setup script's marker is the fast, synchronous readiness signal;
    // prime() adds interpreter probing for externally provided environments.
    const marker = this.marker();
    const engine = {
      ready: Boolean(marker.version) || this.engine.ready === true,
      version: marker.version || this.engine.version || '',
      error: marker.version ? '' : (this.engine.error || ''),
    };
    const file = this.readConfigFile();
    const value = file.value || {};
    const baseUrl = typeof value.base_url === 'string' ? value.base_url.trim() : '';
    const model = typeof value.model === 'string' ? value.model.trim() : '';
    const hasApiKey = Boolean(value.api_key);
    const modelReady = /^https?:\/\//i.test(baseUrl) && Boolean(model) && !PLACEHOLDER_MODEL.test(model) && hasApiKey;
    const missing = { python: !python, engine: !engine.ready, config: !file.exists, model: !modelReady };
    return {
      platform: this.platform,
      platformOk,
      ready: platformOk && !missing.python && !missing.engine && !missing.model,
      running: this.running,
      phase: this.phase,
      message: this.message,
      error: this.error,
      configError: file.error,
      elapsedSeconds: this.running && this.startedAt ? Math.max(0, Math.round((this.now() - this.startedAt) / 1000)) : 0,
      log: this.log.slice(-6),
      missing,
      engine,
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
      this.engine = { ready: false, version: '', error: '', probed: false };
      void this.prime();
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
