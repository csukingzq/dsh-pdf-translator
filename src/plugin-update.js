import gt from 'semver/functions/gt.js';
import valid from 'semver/functions/valid.js';
import metadata from '../package.json' with { type:'json' };

export const pluginName = metadata.name;
export const currentVersion = metadata.version;
const api = 'dsh-market/api/v1/';
const schema = 'dsh-market/update-api/v1';

async function market(route, options = {}) {
  const url = new URL(api + route, document.baseURI);
  const response = await fetch(url, { credentials:'same-origin', mode:'same-origin', cache:'no-store',
    signal:AbortSignal.timeout(30000), ...options });
  const body = await response.json();
  if (!response.ok || body.schema !== schema) throw Error(body.error || '插件市场更新服务不可用。');
  return body;
}

export async function checkPluginUpdate(manual = false) {
  let capabilities;
  try { capabilities = await market('capabilities'); } catch { /* Older or absent Market. */ }
  if (capabilities?.features?.check) {
    const {package:pkg} = await market('updates?name='+pluginName+(manual?'&force=1':''));
    if (pkg?.name !== pluginName || !valid(pkg.latestVersion) || !valid(pkg.installedVersion))
      throw Error('插件市场暂未取得可比较的版本，请稍后重新检查。');
    return {installed:pkg.installedVersion, latest:pkg.latestVersion,
      newer:gt(pkg.latestVersion,pkg.installedVersion),
      installable:Boolean(capabilities.features.update && capabilities.features.progress && pkg.updateAvailable)};
  }
  if (!manual) return null;
  const response = await fetch('https://registry.npmjs.org/'+pluginName+'/latest',
    {credentials:'omit', cache:'no-store', signal:AbortSignal.timeout(15000)});
  if (!response.ok) throw Error('无法读取 npm 最新版本。');
  const pkg = await response.json();
  if (pkg.name !== pluginName || !valid(pkg.version)) throw Error('npm 返回了无效的版本。');
  return {installed:currentVersion,latest:pkg.version,newer:gt(pkg.version,currentVersion),installable:false};
}

export async function startPluginUpdate() {
  const result = await market('updates', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({packageName:pluginName})});
  const id = result.operation?.operationId ?? result.operationId;
  if (typeof id !== 'string' || !id) throw Error('插件市场未返回更新任务编号。');
  return id;
}

export async function pollPluginUpdate(id, target) {
  const {operation} = await market('operations?operationId='+encodeURIComponent(id));
  if (operation?.operationId !== id || operation.packageName !== pluginName) throw Error('无法识别更新任务。');
  if (['queued','running'].includes(operation.state)) return null;
  if (operation.state !== 'succeeded') throw Error(operation.failure?.message || '更新已取消或回滚。');
  if (!valid(operation.installedVersion) || gt(target,operation.installedVersion))
    throw Error('安装版本与更新目标不符，请在插件市场检查。');
  return '已安装 '+operation.installedVersion+'。'+(operation.outcome?.restartRequired?'请重启 DSH。':
    operation.outcome?.refreshRequired?'请刷新页面。':'');
}
