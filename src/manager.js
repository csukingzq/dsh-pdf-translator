import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { randomUUID, createHash } from 'node:crypto';
import { runPython } from './runner.js';
import { resolveDataDir } from './paths.js';
import { translateSchema } from './contract.js';
import {pickNative} from './native-picker.js';
import {ReviewController, completionPolicy} from './review.js';

const activeStates = new Set(['preparing', 'running', 'stopping']);
const phases = {preparing:'准备', recognizing:'AI 识别与翻译', validating:'校验译文', assembling:'组装译文', compiling:'编译 PDF', exporting:'导出成果', completed:'完成'};
export function progressText(p) {
  return `${phases[p.phase] || p.phase} · ${p.completed || 0}/${p.total || 0} 页 · 缓存 ${p.cached || 0} 页`;
}
export class TranslatorManager {
  constructor(ctx, config = {}, runner = runPython, picker = pickNative) {
    this.ctx=ctx; this.config=config; this.runner=runner;
    this.dataDir=path.resolve(resolveDataDir(config));
    this.stateFile=path.join(this.dataDir,'work','plugin-state.json');
    this.state={outputDir:path.resolve(config.outputDir || path.join(this.dataDir,'outputs')), configured:false, aiReview:false, tasks:[]};
    this.active=null; this.busy=false; this.closed=false; this.tokens=new Map(); this.controllers=new Set();
    this.panelRequests=new Map();
    this.picker=picker; this.pickerController=null;
    this.review=new ReviewController(this);
    this.writeChain=Promise.resolve(); this.ready=this.load();
    // Keep errors available to panel operations without an unhandled Host rejection.
    this.ready.catch(()=>{});
  }
  async load() {
    try { this.state=JSON.parse(await fs.readFile(this.stateFile,'utf8')); }
    catch(e){ if(e.code!=='ENOENT') throw new Error('插件状态文件无法读取，请保留文件并检查：'+this.stateFile); }
    this.state.aiReview=this.state.aiReview===true;
    const journals=path.join(this.dataDir,'work','review-transactions');
    try{if((await fs.readdir(journals)).length)await this.runner({operation:'reviewRecover'},this.config);}catch(e){if(e.code!=='ENOENT')throw e;}
    for(const task of this.state.tasks) if(['reviewing','repairing'].includes(task.status)) {
      task.status='completed';task.review.status='interrupted';task.review.summary='核验因重启中断，保留最近可用 PDF。';
    } else if(activeStates.has(task.status)) {
      task.status='interrupted'; task.error='应用退出或插件重载导致中断，可手动继续。'; task.finishedAt=Date.now();
    }
  }
  persist() {
    const data=JSON.stringify(this.state,null,2);
    this.writeChain=this.writeChain.catch(()=>{}).then(async()=>{
      await fs.mkdir(path.dirname(this.stateFile),{recursive:true});
      const temp=this.stateFile+'.tmp'; await fs.writeFile(temp,data,'utf8'); await fs.rename(temp,this.stateFile);
    });
    return this.writeChain;
  }
  async outputDirectory(value) {
    if(!path.isAbsolute(value)) throw new Error('请选择输出目录的绝对路径。');
    await fs.mkdir(value,{recursive:true});
    const folder=await fs.realpath(value);
    const cache=path.join(this.dataDir,'work','document-cache');
    let cacheReal=cache; try{cacheReal=await fs.realpath(cache);}catch{}
    const rel=path.relative(cacheReal,folder);
    if(!rel || (!rel.startsWith('..') && !path.isAbsolute(rel))) throw new Error('输出目录不能位于缓存目录内。');
    const probe=path.join(folder,'.write-test-'+randomUUID());
    await fs.writeFile(probe,'',{flag:'wx'}); await fs.unlink(probe);
    return folder;
  }
  async settings(input){await this.ready; const value=typeof input==='string'?{outputDir:input}:input;
    if(value.outputDir!==undefined){this.state.outputDir=await this.outputDirectory(value.outputDir);this.state.configured=true;}
    if(value.aiReview!==undefined)this.state.aiReview=value.aiReview===true;
    await this.persist();return {outputDir:this.state.outputDir,configured:this.state.configured,aiReview:this.state.aiReview};}
  async status(owner){await this.ready;return {outputDir:this.state.outputDir,configured:this.state.configured,
    aiReview:this.state.aiReview,busy:Boolean(this.busy||this.active||this.review.active()),panelRequest:this.panelRequests.get(owner)||null,
    tasks:this.state.tasks.filter(t=>t.owner===owner).slice(-20).reverse()};}
  panel(owner, section='translation', visible=true){
    if(!owner)throw new Error('请在当前会话中打开面板。');
    this.panelRequests.set(owner,{id:randomUUID(),section,visible});
    return {requested:true,section,visible,message:'面板会在当前会话更新；清理仍须用户手动确认。'};
  }
  async inspect(args){return this.runner({...args,operation:'inspect'},this.config);}
  async pick(kind){
    await this.ready;
    if(this.closed)throw new Error('插件正在关闭。');
    if(this.pickerController)throw new Error('已有系统选择窗口打开，请先完成或取消。');
    const controller=new AbortController();this.pickerController=controller;
    try{return await this.picker(kind,kind==='directory'?this.state.outputDir:'',{signal:controller.signal});}
    finally{if(this.pickerController===controller)this.pickerController=null;}
  }
  async start(input, owner, exec={}) {
    const args=translateSchema.parse(input); await this.ready;
    args.aiReview=args.aiReview??this.state.aiReview;
    if(this.closed) throw new Error('插件正在关闭。');
    if(this.active) {
      if(this.active.owner===owner) return {background:true,jobId:this.active.id,existing:true};
      throw new Error('已有其他会话的翻译任务运行，请等待完成。');
    }
    if(this.busy||this.review.active()) throw new Error('正在准备任务、核验或清理缓存，请稍后再试。');
    if(args.background!==false && !owner) throw new Error('请先选择一个会话，再开始后台翻译。');
    this.busy=true;
    try {
      exec.signal?.throwIfAborted();
      const inspected=await this.inspect(args);
      if(this.closed) throw new Error('插件正在关闭。');
      args.pdf=inspected.path; args.outputDir=await this.outputDirectory(args.outputDir || this.state.outputDir);
      const identity=createHash('sha256').update(await fs.readFile(args.pdf)).digest('hex').slice(0,16);
      const task={id:randomUUID(),owner:owner || '',identity,args,aiReview:args.aiReview,status:'preparing',startedAt:Date.now(),
        progress:{phase:'preparing',completed:0,total:inspected.selected_pages.length,cached:0}};
      const controller=new AbortController(); this.controllers.add(controller);
      const run=(handle)=>{
        task.id=handle?.id || task.id; task.status='running'; this.active=task; this.state.tasks.push(task);
        let lastWrite=0;
        const pending=(async()=>{
          const signal=args.background===false && exec.signal ? AbortSignal.any([exec.signal,controller.signal]) : controller.signal;
          try {
            await this.persist();
            const result=await this.runner({...args,operation:'translate'},this.config,signal,p=>{
              task.progress=p;
              const now=Date.now();
              if(now-lastWrite>500 || p.phase==='completed') {lastWrite=now;handle?.updateProgress(progressText(p));void this.persist().catch(()=>{});}
            });
            task.result={...result,jobId:task.id,aiReview:task.aiReview,completionPolicy:completionPolicy(task.aiReview)};
            task.status=task.aiReview?'reviewing':'completed';
            if(task.aiReview)task.review={status:'pending',rounds:0,version:null};
            return {status:'completed',result:JSON.stringify(task.result),detail:task.aiReview?'PDF 已生成；请用 pdf_review 核验，最多修复两轮':'翻译完成；AI 核验关闭，读取一次结果后直接附 PDF 回复'};
          } catch(e){task.status=controller.signal.aborted || exec.signal?.aborted && args.background===false?'killed':'failed';task.error=e.message;
            return {status:task.status,detail:e.message};
          } finally {task.finishedAt=Date.now();this.active=null;this.controllers.delete(controller);await this.persist();}
        })();
        this.pending=pending;
        return {done:pending,cancel:()=>{task.status='stopping';controller.abort();void this.persist().catch(()=>{});}};
      };
      if(args.background===false) {
        this.busy=false;
        const outcome=await run().done;
        if(outcome.status!=='completed') throw new Error(outcome.detail);
        return task.result;
      }
      const jobs=this.ctx.get('jobs');
      if(!jobs) {this.controllers.delete(controller);throw new Error('当前 Harness 未启用后台任务服务。');}
      // Cancellation after publication belongs to the job, not to the chat tool call.
      exec.signal?.throwIfAborted();
      try {
        const jobId=jobs.start({kind:'pdf',label:path.basename(args.pdf),owner,
          ...(exec.callId?{toolCall:{callId:exec.callId,rootCallId:exec.rootCallId || exec.callId}}:{}),run});
        return {background:true,jobId,pages:inspected.selected_pages.length,outputDir:args.outputDir};
      } catch(e){this.controllers.delete(controller);throw e;}
    } finally{this.busy=false;}
  }
  async cancel(owner,id){await this.ready;const task=this.state.tasks.find(t=>t.id===id&&t.owner===owner);
    if(!task)throw new Error('找不到当前会话的任务。');
    if(['reviewing','repairing'].includes(task.status))return this.review.cancel(task);
    if(!activeStates.has(task.status))return {status:task.status};
    this.ctx.get('jobs').kill(id,owner,'用户取消');return {status:'stopping'};
  }
  async caches(){await this.ready;const result=await this.runner({operation:'cacheList'},this.config);
    return {entries:result.entries.map(r=>({...r,busy:this.active?.identity===r.id||this.review.active()?.identity===r.id})),cleaningDisabled:Boolean(this.active||this.busy||this.review.active())};}
  async prepareClear(identity){
    const {entries}=await this.caches();const row=entries.find(r=>r.id===identity);
    if(!row)throw new Error('该文档缓存不存在。');
    if(row.blocked||this.active||this.busy||this.review.active())throw new Error(row.blocked || '请等待翻译任务结束后清理缓存。');
    const token=randomUUID();this.tokens.set(token,{identity,expires:Date.now()+120000});
    return {...row,token,message:'清理后再次翻译可能重新调用 AI。原 PDF 和导出成果会保留。'};
  }
  async clear(identity,token){
    const choice=this.tokens.get(token);this.tokens.delete(token);
    if(!choice||choice.identity!==identity||choice.expires<Date.now())throw new Error('清理确认已过期，请重新选择文档。');
    if(this.active||this.busy||this.review.active())throw new Error('翻译运行中，暂不能清理缓存。');
    this.busy=true;
    try{return await this.runner({operation:'cacheClear',identity},this.config);}finally{this.busy=false;}
  }
  async browse(folder, directories=false){
    if(folder===''){
      const drives=process.platform==='win32'?(await Promise.all('ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('').map(async c=>{const p=c+':\\';try{await fs.access(p);return {name:p,path:p,directory:true};}catch{return null;}}))).filter(Boolean):[{name:'/',path:'/',directory:true}];
      return {path:'',parent:null,entries:drives,truncated:false};
    }
    folder=folder||os.homedir();if(!path.isAbsolute(folder))throw new Error('请输入绝对路径。');
    folder=await fs.realpath(folder);
    const all=(await fs.readdir(folder,{withFileTypes:true})).filter(d=>!d.isSymbolicLink()&&(d.isDirectory()||!directories&&d.isFile()&&/\.pdf$/i.test(d.name)))
      .sort((a,b)=>Number(b.isDirectory())-Number(a.isDirectory())||a.name.localeCompare(b.name,'zh'));
    return {path:folder,parent:path.dirname(folder)===folder?'':path.dirname(folder),truncated:all.length>500,
      entries:all.slice(0,500).map(d=>({name:d.name,path:path.join(folder,d.name),directory:d.isDirectory()}))};
  }
  async dispose(){this.closed=true;this.pickerController?.abort();for(const c of this.controllers)c.abort();await this.pending;await this.review.pending;await this.writeChain;}
}
