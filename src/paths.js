import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const has = (file) => {
  try { return fs.existsSync(file); } catch { return false; }
};
const dshHome = (env) => path.resolve(env.DSH_HOME || path.join(os.homedir(), '.dsh'));

// Installed packages are replaced on update. Keep user state outside the
// package unless this checkout already used the old in-package location.
export function resolveDataDir(config = {}, options = {}) {
  const pluginRoot = options.pluginRoot || root;
  const env = options.env || process.env;
  if (config.dataDir) return path.resolve(config.dataDir);
  if (env.DSH_PDF_DATA_DIR) return path.resolve(env.DSH_PDF_DATA_DIR);
  if (has(path.join(pluginRoot, 'config.json')) || has(path.join(pluginRoot, 'work', 'plugin-state.json'))) {
    return path.resolve(pluginRoot);
  }
  return path.join(dshHome(env), 'dsh-pdf-translator');
}

export function resolveConfigPath(config = {}, dataDir = resolveDataDir(config), options = {}) {
  const pluginRoot = options.pluginRoot || root;
  const env = options.env || process.env;
  if (config.configPath) return path.resolve(config.configPath);
  if (env.DSH_PDF_CONFIG) return path.resolve(env.DSH_PDF_CONFIG);
  const persistent = path.join(dataDir, 'config.json');
  const legacy = path.join(pluginRoot, 'config.json');
  if (!has(persistent) && path.resolve(pluginRoot) !== path.resolve(dataDir) && has(legacy)) return legacy;
  return persistent;
}

export function resolvePythonPath(config = {}, dataDir = resolveDataDir(config), options = {}) {
  const pluginRoot = options.pluginRoot || root;
  const env = options.env || process.env;
  if (config.pythonPath) return config.pythonPath;
  if (env.DSH_PDF_PYTHON) return env.DSH_PDF_PYTHON;
  const names = process.platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python'];
  for (const base of [dataDir, pluginRoot]) {
    const candidate = path.join(base, '.venv', ...names);
    if (has(candidate)) return candidate;
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

export function resolveRuntimeDir(config = {}, dataDir = resolveDataDir(config), options = {}) {
  const pluginRoot = options.pluginRoot || root;
  const env = options.env || process.env;
  if (env.DSH_PDF_RUNTIME_DIR) return path.resolve(env.DSH_PDF_RUNTIME_DIR);
  const persistent = path.join(dataDir, 'runtime');
  if (has(persistent)) return persistent;
  const legacy = path.join(pluginRoot, 'runtime');
  if (has(legacy)) return legacy;
  return persistent;
}

export function setupCommand(pluginRoot = root) {
  return `powershell -ExecutionPolicy Bypass -File "${path.join(pluginRoot, 'scripts', 'setup.ps1')}"`;
}
