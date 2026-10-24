import { spawn } from 'node:child_process';
import path from 'node:path';
import {
  root,
  resolveDataDir,
  resolveConfigPath,
  resolvePythonPath,
  resolveRuntimeDir,
  setupCommand,
} from './paths.js';

export { root };

export function pythonPath(config = {}) {
  return resolvePythonPath(config);
}

export function runPython(request, config = {}, signal, onProgress) {
  signal?.throwIfAborted();
  const dataDir = resolveDataDir(config);
  const configPath = resolveConfigPath(config, dataDir);
  const runtimeDir = resolveRuntimeDir(config, dataDir);
  const python = pythonPath(config);
  return new Promise((resolve, reject) => {
    const child = spawn(python, ['-u', path.join(root, 'work/cli.py')], {
      cwd: root, windowsHide: true, shell: false,
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUTF8: '1',
        DSH_PDF_DATA_DIR: dataDir,
        DSH_PDF_RUNTIME_DIR: runtimeDir,
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    let stdout = '', stderr = '', stopped, streamedResult, streamError, stopTree=Promise.resolve();
    const stop = (reason) => {
      if (stopped) return;
      stopped = reason;
      if (process.platform === 'win32' && child.pid) {
        // Kill the compiler too, before releasing the Python lock.
        const killer = spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
        stopTree=new Promise(done=>{killer.once('close',done);killer.once('error',done);});
        killer.on('error', () => child.kill());
        killer.on('exit', code => { if (code) child.kill(); });
      } else child.kill('SIGKILL');
    };
    const abort = () => stop(new Error('翻译已取消，已完成的页面缓存保留。'));
    const timer = setTimeout(() => stop(new Error('翻译超时，已完成的页面缓存保留。')), config.timeoutMs || 3600000);
    const cleanup = () => { clearTimeout(timer); signal?.removeEventListener('abort', abort); };
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) abort();
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (data) => {
      stdout += data;
      if (onProgress) {
        let newline;
        while ((newline = stdout.indexOf('\n')) >= 0) {
          const line = stdout.slice(0, newline).trim(); stdout = stdout.slice(newline + 1);
          if (!line) continue;
          try {
            const event = JSON.parse(line);
            if (event.type === 'progress') onProgress(event.value);
            else if (event.type === 'result') streamedResult = event.value;
            else if (event.type === 'error') streamError = event.error;
          } catch { stop(new Error('无效的 Python 进度事件。')); }
        }
      }
      if (stdout.length > 2_000_000) stop(new Error('Python 返回数据过大。'));
    });
    child.stderr.on('data', (data) => { stderr = (stderr + data).slice(-8000); });
    child.on('error', () => { cleanup(); reject(new Error(`无法启动 Python（${python}）。请运行 ${setupCommand()}，或在插件配置中设置 pythonPath。`)); });
    child.on('close', async (code) => {
      cleanup();
      await stopTree;
      if (stopped) return reject(stopped);
      let result;
      if (streamError) return reject(new Error(streamError));
      try { result = onProgress ? streamedResult : JSON.parse(stdout.trim()); if (!result) throw new Error(); }
      catch { return reject(new Error(`Python 未返回有效结果（退出码 ${code}）。请运行 ${setupCommand()} 检查环境。${stderr.includes('ModuleNotFoundError') ? ' 缺少 Python 依赖。' : ''}`)); }
      if (code !== 0 || result.error) return reject(new Error(result.error || `Python 退出码 ${code}`));
      resolve(result);
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify({ ...request,
      events: Boolean(onProgress),
      configPath, dataDir }));
  });
}
