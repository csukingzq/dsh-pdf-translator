import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { Context, Service } from '@deepseek-ai/cordis';
import Jobs from '@deepseek-ai/dsh-jobs-local';
import Registry from '@deepseek-ai/dsh-typert-registry';
import Gateway from '@deepseek-ai/dsh-api-gateway';
import { TranslatorManager } from '../src/manager.js';
import { TranslatorService } from '../src/service.js';
import { root,runPython } from '../src/runner.js';
import * as ClientRemote from '@deepseek-ai/dsh-api-gateway/client';
import { remoteInfo } from '../src/contract.js';

const pause=()=>new Promise(r=>setTimeout(r,25));
const fixture=path.join(root,'tests/fixtures/vision-sample.pdf');
async function temp(t){const dir=await fs.mkdtemp(path.join(os.tmpdir(),'pdf-plugin-test-'));t.after(async()=>{
  assert.ok(path.resolve(dir).startsWith(path.resolve(os.tmpdir())+path.sep+'pdf-plugin-test-'));
  await fs.rm(dir,{recursive:true,force:true});});return dir;}
async function jobsContext(){
  const ctx=new Context();const owner={id:'session-a',ctx,session:{append:()=>{}}};
  new class extends Service{constructor(){super(ctx,'agents');}get(id){return id===owner.id?owner:undefined;}};
  ctx.plugin(Jobs);await pause();ctx.jobs.attachController('test-controller');return ctx;
}
function controlledRunner(){
  let resolve, reject, progress;const calls=[];
  return {calls,get progress(){return progress;},complete:v=>resolve(v),
    run:async(r,c,signal,onProgress)=>{
      calls.push(r);
      if(r.operation==='inspect')return {path:fixture,pages:1,selected_pages:[1]};
      if(r.operation==='cacheList')return {entries:[{id:'0123456789abcdef',name:'sample.pdf',bytes:1}]};
      if(r.operation==='cacheClear')return {cleared:true};
      progress=onProgress;
      return new Promise((a,b)=>{resolve=a;reject=b;signal?.addEventListener('abort',()=>reject(new Error('cancelled')),{once:true});});
    }};
}

test('native Harness job: ownership, progress, duplicate prevention, and chat cancellation independence',async t=>{
  const dir=await temp(t),ctx=await jobsContext(),runner=controlledRunner();
  const m=new TranslatorManager(ctx,{dataDir:dir},runner.run);t.after(async()=>{await m.dispose();await ctx.fiber.dispose();});
  const invocation=new AbortController();
  const result=await m.start({pdf:fixture},'session-a',{signal:invocation.signal,callId:'nested',rootCallId:'root'});
  await pause();invocation.abort();
  assert.equal(ctx.jobs.get(result.jobId,'session-a').status,'running');
  runner.progress({phase:'recognizing',completed:1,total:1,cached:1});
  assert.match(ctx.jobs.get(result.jobId,'session-a').progress,/1\/1/);
  assert.throws(()=>ctx.jobs.get(result.jobId,'session-b'),/another session/);
  assert.equal((await m.start({pdf:fixture},'session-a')).jobId,result.jobId);
  assert.equal((await m.status('session-b')).tasks.length,0);
  const originalOutput=(await m.status('session-a')).tasks[0].args.outputDir;
  await m.settings(path.join(dir,'新的输出目录'));
  assert.equal((await m.status('session-a')).tasks[0].args.outputDir,originalOutput);
  assert.equal(runner.calls.find(r=>r.operation==='translate').outputDir,originalOutput);
  await assert.rejects(m.prepareClear('0123456789abcdef'),/结束/);
  runner.complete({output:'translated.pdf',status:'complete'});
  await m.pending;await pause();
  assert.equal(ctx.jobs.get(result.jobId,'session-a').status,'completed');
  assert.equal(JSON.parse(ctx.jobs.read(result.jobId,'session-a').result).output,'translated.pdf');
  assert.equal(runner.calls.filter(r=>r.operation==='translate').length,1);
});

test('native cancellation waits for producer and leaves resumable task state',async t=>{
  const dir=await temp(t),ctx=await jobsContext(),runner=controlledRunner(),m=new TranslatorManager(ctx,{dataDir:dir},runner.run);
  t.after(async()=>{await m.dispose();await ctx.fiber.dispose();});
  const job=await m.start({pdf:fixture},'session-a');await pause();await m.cancel('session-a',job.jobId);await m.pending;await pause();
  assert.equal(ctx.jobs.get(job.jobId,'session-a').status,'killed');
  assert.equal((await m.status('session-a')).tasks[0].status,'killed');
});

test('output defaults persist; cache deletion requires a fresh one-use user confirmation',async t=>{
  const dir=await temp(t),ctx=new Context(),runner=controlledRunner(),m=new TranslatorManager(ctx,{dataDir:dir},runner.run);
  t.after(()=>m.dispose());
  const chosen=path.join(dir,'中文 输出');await m.settings(chosen);
  const resolvedChosen=await fs.realpath(chosen);
  assert.equal((await m.status()).outputDir,resolvedChosen);
  await assert.rejects(m.outputDirectory(path.join(dir,'work/document-cache/nested')),/缓存/);
  await assert.rejects(m.clear('0123456789abcdef','made-up'),/确认/);
  const selection=await m.prepareClear('0123456789abcdef');
  assert.equal((await m.clear(selection.id,selection.token)).cleared,true);
  await assert.rejects(m.clear(selection.id,selection.token),/确认/);
  const restored=new TranslatorManager(ctx,{dataDir:dir},runner.run);await restored.ready;
  assert.equal((await restored.status()).outputDir,resolvedChosen);await restored.dispose();await ctx.fiber.dispose();
});

test('restart marks unfinished jobs interrupted and retains their original parameters',async t=>{
  const dir=await temp(t);await fs.mkdir(path.join(dir,'work'));
  await fs.writeFile(path.join(dir,'work/plugin-state.json'),JSON.stringify({outputDir:dir,configured:true,tasks:[{id:'old',owner:'s',status:'running',args:{pdf:fixture,pages:'1'}}]}));
  const ctx=new Context(),m=new TranslatorManager(ctx,{dataDir:dir});
  const status=await m.status('s');assert.equal(status.tasks[0].status,'interrupted');assert.equal(status.tasks[0].args.pages,'1');await m.dispose();await ctx.fiber.dispose();
});

test('strict Harness Gateway dispatch accepts valid requests and rejects extra fields/non-owner clients',async t=>{
  const dir=await temp(t),ctx=new Context();
  new class extends Service{constructor(){super(ctx,'remoteAccess');}decide(){return {allowed:true};}};
  ctx.plugin(Registry);ctx.plugin(Gateway);await pause();
  const selections=[];
  const manager=new TranslatorManager(ctx,{dataDir:dir},runPython,async kind=>{selections.push(kind);return {cancelled:true};});new TranslatorService(ctx,manager);
  const peer={principal:{kind:'owner'},signal:new AbortController().signal,disposed:false};
  const invoke=request=>ctx.typertGateway.invoke({namespace:'pdfTranslator',method:'call',args:{request},peer});
  assert.equal((await invoke({action:'status'})).tasks.length,0);
  assert.deepEqual(await invoke({action:'pick',kind:'pdf'}),{cancelled:true});
  await assert.rejects(invoke({action:'pick',kind:'executable'}));
  await assert.rejects(invoke({action:'status',deleteEverything:true}),/input|argument|field/i);
  await assert.rejects(invoke({action:'clear',identity:'../outputs',token:'x'}));
  peer.principal={kind:'guest'};await assert.rejects(invoke({action:'status'}),/桌面用户/);
  await assert.rejects(invoke({action:'pick',kind:'directory'}),/桌面用户/);
  assert.deepEqual(selections,['pdf']);
  await manager.dispose();await ctx.fiber.dispose();
});

test('one native picker at a time; cancellation preserves settings; disposal aborts picker',async t=>{
  const dir=await temp(t),ctx=new Context();let resolve;
  const picker=(_kind,_initial,{signal})=>new Promise((a,b)=>{resolve=a;signal.addEventListener('abort',()=>b(Error('aborted')),{once:true});});
  const m=new TranslatorManager(ctx,{dataDir:dir},runPython,picker);
  await m.ready;const original=(await m.status()).outputDir;
  const pending=m.pick('directory');await pause();
  await assert.rejects(m.pick('pdf'),/已有系统选择窗口/);
  resolve({cancelled:true});assert.deepEqual(await pending,{cancelled:true});
  assert.equal((await m.status()).outputDir,original);
  const next=m.pick('pdf');const rejected=assert.rejects(next,/aborted/);await pause();await m.dispose();await rejected;
  await ctx.fiber.dispose();
});

test('streaming Python bridge and legacy JSON produce identical inspection results',async()=>{
  const request={operation:'inspect',pdf:fixture};
  const [plain,streamed]=await Promise.all([runPython(request),runPython(request,{},undefined,()=>{})]);
  assert.deepEqual(streamed,plain);
});

test('real Harness browser remote mount calls the real Host gateway',async t=>{
  const dir=await temp(t),host=new Context(),client=new Context();
  new class extends Service{constructor(){super(host,'remoteAccess');}decide(){return {allowed:true};}};
  host.plugin(Registry);host.plugin(Gateway);await pause();
  const manager=new TranslatorManager(host,{dataDir:dir});new TranslatorService(host,manager);
  const peer={principal:{kind:'owner'},signal:new AbortController().signal,disposed:false};
  new class extends Service{
    constructor(){super(client,'connection');}
    interactions='none';
    rpc={open:()=>{},call:async(_base,endpoint,payload)=>{
      const [namespace,method]=endpoint.split('/');
      return {ok:true,value:await host.typertGateway.invoke({namespace,method,args:payload.args,peer})};
    }};
  };
  client.plugin(Registry);client.plugin(ClientRemote);await pause();
  await client.remote.$mount(remoteInfo);
  const result=await client.remote.pdfTranslator.call({action:'status'});
  assert.equal(result.ok,true);assert.equal(result.value.outputDir,path.join(dir,'outputs'));
  await client.fiber.dispose();await manager.dispose();await host.fiber.dispose();
});
