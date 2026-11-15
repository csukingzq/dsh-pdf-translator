import React, { useEffect, useState, useRef, useSyncExternalStore } from 'react';
import { createRoot } from 'react-dom/client';
import { remoteInfo } from './contract.js';
import styles from './panel.css';
import {useFloatingPosition} from './use-floating-position.js';
import {pageSelection} from './page-selection.js';
import {bindSessions} from './session-binding.js';
import {PluginUpdatePanel} from './plugin-update-panel.jsx';

export const inject=['slots','remote'];
export function createPanelState(){
  let value={visible:false,sessionId:null};const listeners=new Set();
  return {get:()=>value,subscribe:fn=>{listeners.add(fn);return()=>listeners.delete(fn);},
    set:patch=>{value={...value,...patch};for(const fn of listeners)fn();}};
}
const phaseNames={analyzing_structure:'分析全文结构',recognizing:'逐页识别',translating_paragraphs:'翻译正文段落',validating:'校验译文',assembling:'组装译文',compiling:'编译 PDF',reviewing:'AI 核验',repairing:'修复排版',preparing:'准备',analyzing:'解析版式',glossary:'提取术语',translating:'翻译段落',typesetting:'排版生成 PDF',exporting:'导出成果',completed:'完成'};
const activeStates=new Set(['running','preparing','stopping','reviewing','repairing']);
const fileName=p=>p?.split(/[\\/]/).pop() || '';
const formatSize=n=>n>=1048576?(n/1048576).toFixed(1)+' MB':(n/1024).toFixed(1)+' KB';

function Dialog({title,onClose,pending,children}){
  const ref=useRef(null);
  useEffect(()=>{
    const node=ref.current;
    if(node.showModal)node.showModal();else node.setAttribute('open','');
    return()=>{node.close?.();};
  },[]);
  return <dialog ref={ref} className="pdf-dialog" aria-label={title} aria-modal="true" onCancel={e=>{e.preventDefault();if(!pending)onClose();}}>
    <div className="pdf-row pdf-dialog-title"><strong>{title}</strong><button disabled={pending} onClick={onClose} aria-label="关闭窗口">×</button></div>
    {children}
  </dialog>;
}

export function Panel({store,call,ensureSession}){
  const ui=useSyncExternalStore(store.subscribe,store.get);
  const entryPosition=useFloatingPosition('entry',!ui.visible);
  const panelPosition=useFloatingPosition('panel',ui.visible,entryPosition.getPosition);
  const [state,setState]=useState({tasks:[],outputDir:'',configured:true,busy:false,setup:null});
  const [dialog,setDialog]=useState(null),[pages,setPages]=useState('全部'),[manualPath,setManualPath]=useState('');
  const [error,setError]=useState(''),[pending,setPending]=useState(false),[notice,setNotice]=useState('');
  const [caches,setCaches]=useState(null),[confirmation,setConfirmation]=useState(null);
  const [configForm,setConfigForm]=useState({baseUrl:'',model:'',apiKey:''});
  const lastPanelRequest=useRef(null),lock=useRef(false),generation=useRef(0);
  const current=state.tasks.find(t=>activeStates.has(t.status));
  const selection=dialog?.kind==='translate'?pageSelection(pages,dialog.info.pages):null;
  const engine=state.engine||'pdf2zh';
  const isOcr=engine==='ocr';
  const [ocrOptions,setOcrOptions]=useState({imageQuality:'safe',thinking:'auto',renderOnly:false});
  const setup=state.setups?.[engine]||state.setup;
  const setupReady=!setup||setup.ready!==false||(isOcr&&ocrOptions.renderOnly&&setup.runtimeReady);
  const needsEnvironment=Boolean(setup&&(setup.missing?.python||setup.missing?.engine));
  function close(){setDialog(null);setConfirmation(null);setError('');}
  async function action(fn){
    if(lock.current)return;
    lock.current=true;setError('');setNotice('');setPending(true);
    const version=generation.current;
    try{return await fn(()=>version===generation.current);}
    catch(e){if(version===generation.current)setError(e.message);}
    finally{lock.current=false;setPending(false);}
  }
  async function refresh(){
    const owner=store.get().sessionId;
    const next=await call({action:'status',...(owner?{sessionId:owner}:{})});
    if(store.get().sessionId===owner)setState(next);
    return next;
  }
  async function loadCaches(){setCaches(await call({action:'caches'}));}
  function openConfig(){
    const config=setup?.config||{};
    setConfigForm({baseUrl:config.baseUrl||'https://api.deepseek.com/v1',model:config.model||'',apiKey:''});
    setDialog({kind:'config'});
  }
  async function runSetup(){await call({action:'setupStart',engine});await refresh();}
  async function cancelSetup(){await call({action:'setupCancel'});await refresh();}
  async function saveConfig(){
    const result=await call({action:'saveConfig',engine,baseUrl:configForm.baseUrl.trim(),model:configForm.model.trim(),apiKey:configForm.apiKey});
    setState(prev=>prev.setup?{...prev,setup:{...prev.setup,config:result,missing:{...prev.setup.missing,model:false}}}:prev);
    close();setNotice('模型配置已保存。');await refresh();
  }
  useEffect(()=>{
    let alive=true,timer;
    async function poll(){
      try{const next=await call({action:'status',...(ui.sessionId?{sessionId:ui.sessionId}:{})});if(alive)setState(next);}
      catch(e){if(alive)setError(e.message);}
      if(alive)timer=setTimeout(poll,ui.visible?1000:5000);
    }
    poll();return()=>{alive=false;clearTimeout(timer);};
  },[ui.visible,ui.sessionId,call]);
  useEffect(()=>{
    generation.current++;close();setCaches(null);setState({tasks:[],outputDir:'',busy:false,setup:null});
  },[ui.sessionId]);
  useEffect(()=>{
    const request=state.panelRequest;
    if(!request||request.id===lastPanelRequest.current)return;
    lastPanelRequest.current=request.id;store.set({visible:request.visible});
    if(!request.visible){close();return;}
    if(request.section==='cache'){setDialog({kind:'cache'});action(loadCaches);}
    if(request.section==='outputs')setNotice('点击“选择输出目录”可更改后续任务的保存位置。');
  },[state.panelRequest,store]);
  async function acceptPath(kind,value,valid){
    if(kind==='pdf'){
      const info=await call({action:'inspect',pdf:value.trim(),pages:'all'});
      if(valid()){setPages('全部');setDialog({kind:'translate',info});}
    }else{
      const result=await call({action:'settings',outputDir:value.trim()});
      if(valid()){setState(prev=>({...prev,...result}));close();setNotice('输出目录已保存。');}
    }
  }
  async function choose(kind,valid){
    if(kind==='pdf'){
      const latest=await refresh();
      if(!valid())return;
      if(latest.busy){setNotice('已有翻译任务运行或正在准备，请在原生任务中查看。');return;}
    }
    let result;
    try{result=await call({action:'pick',kind});}
    catch(e){if(valid()){setManualPath(kind==='directory'?state.outputDir:'');setDialog({kind:'manual',target:kind});setError(e.message);}return;}
    if(!valid()||result.cancelled)return;
    try{await acceptPath(kind,result.path,valid);}
    catch(e){if(valid()){setManualPath(result.path);setDialog({kind:'manual',target:kind});}throw e;}
  }
  async function start(valid){
    if(!setupReady)throw new Error('请先完成运行环境准备和模型配置。');
    if(selection.error)throw new Error(selection.error);
    const args={pdf:dialog.info.path,pages:selection.pages,workers:4,outputDir:state.outputDir,engine,...(isOcr?{...ocrOptions,aiReview:state.aiReview===true}:{})};
    const sessionId=store.get().sessionId || await ensureSession?.();
    if(!sessionId)throw new Error('无法建立会话，请稍后重试。');
    if(store.get().sessionId!==sessionId)throw new Error('当前会话已切换，未启动翻译。');
    await call({action:'start',sessionId,args});
    if(store.get().sessionId===sessionId){close();await refresh();}
  }
  const progress=current?.progress;
  const percent=Math.max(0,Math.min(100,Number(progress?.percent) || (progress?.total?Math.round(100*(progress.completed||0)/progress.total):0)));
  return <div className="pdf-translator-ui">
    <button className="pdf-entry" hidden={ui.visible} ref={entryPosition.ref} style={entryPosition.style} {...entryPosition.handle}
      title="点击打开；拖动或使用方向键移动" aria-expanded={ui.visible} onClick={()=>store.set({visible:true})}>PDF 翻译{current?' ·':''}</button>
    <section className="pdf-panel" ref={panelPosition.ref} style={panelPosition.style} aria-label="PDF 翻译面板" hidden={!ui.visible}>
      <header {...panelPosition.handle}><strong className="pdf-drag-handle" tabIndex={0} onKeyDown={panelPosition.handle.onKeyDown} title="拖动或使用方向键移动面板" aria-label="移动 PDF 翻译面板">⠿ PDF 翻译</strong><button onClick={()=>store.set({visible:false})}>收起</button></header>
      <div className="pdf-body">
        <label htmlFor="pdf-engine">翻译引擎<select id="pdf-engine" value={engine} disabled={pending||state.busy} onChange={e=>{const value=e.target.value;action(async()=>{await call({action:'settings',engine:value});setOcrOptions(prev=>({...prev,renderOnly:false}));await refresh();});}}>
          <option value="pdf2zh">Zotero PDF2zh（推荐，保留版式）</option><option value="ocr">OCR 识图（LaTeX 重排）</option>
        </select></label>
        <small>{isOcr?'适合扫描件和需要重排的文档；模型须支持图片输入。':'使用 pdf2zh-next / BabelDOC；保留公式和版式，输出单语及双语 PDF。'}</small>
        {isOcr&&<label><input type="checkbox" checked={state.aiReview===true} disabled={pending||state.busy} onChange={e=>{const aiReview=e.target.checked;action(async()=>{await call({action:'settings',aiReview});await refresh();});}}/>翻译后 AI 核验（最多修复两轮）</label>}
        {setup&&!setup.ready&&<div className="pdf-setup" role="status">
          {setup.running?<>
            <strong>正在准备运行环境…</strong>
            <progress aria-label="环境准备进度"/>
            <small>{setup.message||'正在下载并安装组件'}{setup.elapsedSeconds?` · ${setup.elapsedSeconds} 秒`:''}</small>
            <div className="pdf-row"><button disabled={pending} onClick={()=>action(cancelSetup)}>取消</button></div>
          </>:<>
            <strong>{needsEnvironment?'首次使用需要准备运行环境':'还差模型配置'}</strong>
            <small>{needsEnvironment?(isOcr?'安装识图依赖、Pandoc 和 Tectonic，首次编译会联网下载 LaTeX 资源。':'约 1 GB，首次翻译还会下载约 300 MB 模型，需要联网；视网络情况可能需要十几分钟。'):'填写接口地址、模型名称和 API 密钥后即可开始翻译。'}</small>
            {setup.error&&<p role="alert" className="pdf-error">{setup.error}</p>}
            {setup.configError&&<p role="alert" className="pdf-error">{setup.configError}</p>}
            {setup.platformOk===false
              ?<small>当前系统不支持自动安装，仅支持 Windows。</small>
              :needsEnvironment
                ?<button disabled={pending} onClick={()=>action(runSetup)}>{setup.error?'重试准备环境':'一键准备环境'}</button>
                :<button disabled={pending} onClick={openConfig}>填写模型配置</button>}
          </>}
        </div>}
        <div className="pdf-actions">
          <button disabled={pending} onClick={()=>action(valid=>choose('pdf',valid))}>选择 PDF</button>
          <button disabled={pending} onClick={()=>action(valid=>choose('directory',valid))}>选择输出目录</button>
          <button disabled={pending} onClick={openConfig}>模型配置</button>
          <button disabled={pending} onClick={()=>{setDialog({kind:'cache'});setConfirmation(null);action(loadCaches);}}>清理缓存</button>
        </div>
        <PluginUpdatePanel visible={ui.visible} busy={pending||state.busy||Boolean(current)}/>
        <small><a href="https://github.com/csukingzq/dsh-pdf-translator" target="_blank" rel="noreferrer">源码与许可证（AGPL-3.0）</a></small>
        {!dialog&&error&&<p role="alert" className="pdf-error">{error}</p>}
        {notice&&<small role="status">{notice}</small>}
        {pending&&!dialog&&<small>请完成系统选择窗口…</small>}
        {current&&<div className="pdf-task" aria-live="polite">
          <strong title={current.args.pdf}>{fileName(current.args.pdf)}</strong>
          <progress aria-label="翻译进度" max={100} value={percent}/>
          <div className="pdf-row"><small>{current.status==='stopping'?'正在取消':phaseNames[progress?.phase]||'准备'}{progress?.stage?` · ${progress.stage}`:''}</small><small>{percent}%{progress?.elapsedSeconds?` · 已等待 ${progress.elapsedSeconds} 秒`:''}{progress?.total?` · ${progress.completed||0}/${progress.total} ${current?.args.engine==='ocr'?'页':'段'}`:''}</small></div>
          {current?.args.engine!=='ocr'&&progress?.phase==='preparing'&&<small>首次运行会下载 BabelDOC 模型（约 300 MB），可能需要几分钟。</small>}
        </div>}
      </div>
    </section>
    {dialog&&<Dialog title={dialog.kind==='translate'?'确认翻译':dialog.kind==='cache'?'清理缓存':dialog.kind==='config'?'模型配置':dialog.target==='pdf'?'手动输入 PDF 路径':'手动输入输出目录'} pending={pending} onClose={close}>
      {dialog.kind==='translate'&&<>
        <p className="pdf-document" title={dialog.info.path}>{fileName(dialog.info.path)} <small>共 {dialog.info.pages} 页</small></p>
        <label>输出目录<small className="pdf-path">{state.outputDir}</small></label>
        <label htmlFor="pdf-pages">翻译页码<input id="pdf-pages" autoFocus value={pages} placeholder="全部，或 1,3,5-8" onChange={e=>setPages(e.target.value)}/></label>
        {selection.error?<p role="alert" className="pdf-error">{selection.error}</p>:<small>将翻译 {selection.count} 页；留空表示全部。{isOcr?'仅处理所选原文页；LaTeX 重排后输出页数可能变化。':'单语和双语 PDF 只保留所选页面。'}</small>}
        {isOcr&&<details><summary>OCR 高级选项</summary>
          <label>识图质量<select value={ocrOptions.imageQuality} onChange={e=>setOcrOptions({...ocrOptions,imageQuality:e.target.value})}><option value="safe">高保真</option><option value="auto">自动</option><option value="compact">节省流量</option></select></label>
          <label>模型思考<select value={ocrOptions.thinking} onChange={e=>setOcrOptions({...ocrOptions,thinking:e.target.value})}><option value="auto">自动</option><option value="off">关闭</option><option value="on">开启</option></select></label>
          <label><input type="checkbox" checked={ocrOptions.renderOnly} onChange={e=>setOcrOptions({...ocrOptions,renderOnly:e.target.checked})}/>仅用已有 OCR 缓存重新排版（不调用模型）</label>
        </details>}
        {!setupReady&&<small>请先完成运行环境准备和模型配置。</small>}
        {state.busy&&<small>已有任务运行或正在准备，请在原生任务中查看。</small>}
        <div className="pdf-dialog-actions"><button disabled={pending} onClick={close}>取消</button><button className="pdf-primary" disabled={pending||!!selection.error||state.busy||!state.outputDir||!setupReady} onClick={()=>action(start)}>开始翻译</button></div>
      </>}
      {dialog.kind==='manual'&&<>
        <label htmlFor="pdf-manual">{dialog.target==='pdf'?'PDF 绝对路径':'输出目录绝对路径'}<input id="pdf-manual" autoFocus value={manualPath} onChange={e=>setManualPath(e.target.value)}/></label>
        <div className="pdf-dialog-actions"><button disabled={pending} onClick={close}>取消</button><button className="pdf-primary" disabled={pending||!manualPath.trim()} onClick={()=>action(valid=>acceptPath(dialog.target,manualPath,valid))}>{dialog.target==='pdf'?'读取文档':'保存目录'}</button></div>
      </>}
      {dialog.kind==='config'&&<>
        <label htmlFor="pdf-base-url">接口地址<input id="pdf-base-url" autoFocus value={configForm.baseUrl} placeholder="https://api.deepseek.com/v1" onChange={e=>setConfigForm({...configForm,baseUrl:e.target.value})}/></label>
        <label htmlFor="pdf-model">模型名称<input id="pdf-model" value={configForm.model} placeholder={isOcr?'支持图片输入的视觉模型名':'支持文本翻译的模型名'} onChange={e=>setConfigForm({...configForm,model:e.target.value})}/></label>
        <label htmlFor="pdf-api-key">API 密钥<input id="pdf-api-key" type="password" autoComplete="new-password" value={configForm.apiKey} placeholder={setup?.config?.hasApiKey?'已保存，留空保持不变':'请输入密钥'} onChange={e=>setConfigForm({...configForm,apiKey:e.target.value})}/></label>
        <small>密钥保存在本机，仅用于向所配置的模型接口发起请求。两种引擎分别保存模型配置。</small>
        <div className="pdf-dialog-actions"><button disabled={pending} onClick={close}>取消</button><button className="pdf-primary" disabled={pending||!configForm.baseUrl.trim()||!configForm.model.trim()||(!setup?.config?.hasApiKey&&!configForm.apiKey.trim())} onClick={()=>action(saveConfig)}>保存</button></div>
      </>}
      {dialog.kind==='cache'&&<>
        <small>版式引擎使用共享缓存；OCR 缓存可按文档清理。原 PDF 与已导出成果不会删除。</small>
        <button disabled={pending} onClick={()=>action(loadCaches)}>刷新列表</button>
        {(caches?.cleaningDisabled||state.busy)&&<small>翻译或取消任务尚未结束，暂不能清理。</small>}
        {caches?.entries.length===0&&<small>没有缓存记录。</small>}
        <div className="pdf-cache-list">{caches?.entries.map(row=><div className="pdf-cache" key={row.id}>
          <strong title={row.source}>{row.name}</strong><small>{formatSize(row.bytes)} · {row.blocked?'受保护':row.id==='engine'?'可清理':'文档记录'}</small>
          {row.blocked&&<small>{row.blocked}</small>}
          {(row.id==='engine'||row.engine==='ocr')&&<button disabled={pending||state.busy||caches.cleaningDisabled||!!row.blocked} onClick={()=>action(async()=>setConfirmation(await call({action:'prepareClear',identity:row.id})))}>{row.engine==='ocr'?'清理文档缓存':'清理引擎缓存'}</button>}
        </div>)}</div>
        {confirmation&&<div className="pdf-confirm" role="alertdialog" aria-label="确认清理缓存">
          <strong>{confirmation.name} · {formatSize(confirmation.bytes)}</strong><p>{confirmation.message}</p>
          <div className="pdf-dialog-actions"><button disabled={pending} onClick={()=>setConfirmation(null)}>取消</button><button disabled={pending||state.busy||caches?.cleaningDisabled} onClick={()=>action(async()=>{await call({action:'clear',identity:confirmation.id,token:confirmation.token});setConfirmation(null);await loadCaches();})}>确认清理</button></div>
        </div>}
      </>}
      {error&&<p role="alert" className="pdf-error">{error}</p>}
    </Dialog>}
  </div>;
}

export async function apply(ctx){
  await ctx.remote.$mount(remoteInfo);
  // Mount first, then declare the generated namespace on its consuming fiber.
  ctx.inject(['slots','remote','remote.pdfTranslator','uiWorkspace','sessions','workspaces'],ctx=>{
    const store=createPanelState();
    const binding=bindSessions(store,ctx.uiWorkspace,ctx.sessions,ctx.workspaces);
    ctx.effect(()=>binding.dispose);
    const call=async request=>{const response=await ctx.remote.pdfTranslator.call(request);if(!response.ok)throw response.error;return response.value;};
    function Entry(){
      return <button type="button" title="显示或隐藏 PDF 翻译" onClick={()=>store.set({visible:!store.get().visible})}>PDF 翻译</button>;
    }
    ctx.slots.inject('conversation.session.header.actions',()=>ctx.slots.register({name:'conversation.session.header.actions',id:'pdf-translator',order:25},Entry));
    ctx.effect(()=>{
      const css=document.createElement('style');css.textContent=styles;document.head.append(css);
      const node=document.createElement('div');node.dataset.pdfTranslator='';document.body.append(node);
      const root=createRoot(node);root.render(<Panel store={store} call={call} ensureSession={binding.ensure}/>);
      return()=>{root.unmount();node.remove();css.remove();};
    });
  });
}
