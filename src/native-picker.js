import {spawn} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

// Paths travel as base64 data, never as executable PowerShell source.
export function pickNative(kind, initialPath='', {signal, spawnProcess=spawn, platform=process.platform, timeoutMs=300000}={}) {
  if(!['pdf','directory'].includes(kind))return Promise.reject(new Error('无效选择窗口。'));
  if(platform!=='win32')return Promise.reject(new Error('系统选择窗口仅支持 Windows，请手动输入路径。'));
  signal?.throwIfAborted();
  return new Promise((resolve,reject)=>{
    const script=fileURLToPath(new URL('../scripts/pick-path.ps1',import.meta.url));
    const executable=path.join(process.env.SystemRoot||'C:\\Windows','System32','WindowsPowerShell','v1.0','powershell.exe');
    const child=spawnProcess(executable,['-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',script,
      '-Kind',kind,'-InitialPathBase64',Buffer.from(initialPath,'utf8').toString('base64')||'EMPTY'],
    {windowsHide:true,stdio:['ignore','pipe','pipe']});
    let output='',settled=false;
    const finish=(error,result)=>{if(settled)return;settled=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);error?reject(error):resolve(result);};
    const abort=()=>{child.kill();finish(new Error('系统选择窗口已取消。'));};
    const timer=setTimeout(()=>{child.kill();finish(new Error('系统选择窗口等待超时，请重试或手动输入路径。'));},timeoutMs);
    signal?.addEventListener('abort',abort,{once:true});
    if(signal?.aborted)abort();
    child.stdout.setEncoding('utf8');
    child.stdout.on('data',chunk=>{output+=chunk;if(output.length>65536){child.kill();finish(new Error('系统选择窗口返回数据过大。'));}});
    // Drain stderr; do not expose shell diagnostics or environment details to the UI.
    child.stderr.on('data',()=>{});
    child.on('error',()=>finish(new Error('无法打开系统选择窗口，请手动输入路径。')));
    child.on('close',code=>{
      if(settled)return;
      try{
        if(code!==0)throw new Error();
        const result=JSON.parse(output.trim().replace(/^\uFEFF/,''));
        if(result.cancelled===true)finish(null,{cancelled:true});
        else if(result.cancelled===false&&typeof result.path==='string'&&path.win32.isAbsolute(result.path))finish(null,{cancelled:false,path:result.path});
        else throw new Error();
      }catch{finish(new Error('无法读取系统选择结果，请重试或手动输入路径。'));}
    });
  });
}
