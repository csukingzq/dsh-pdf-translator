import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {JSDOM} from 'jsdom';
import {pageSelection} from '../src/page-selection.js';

test('page ranges reject malformed/out-of-bounds selections and normalize empty/all',()=>{
  for(const value of ['', ' ', '全部','ALL','all'])assert.equal(pageSelection(value,8).pages,'all');
  assert.deepEqual(pageSelection('1,3,5-8',8),{pages:'1,3,5,6,7,8',count:6,error:''});
  assert.equal(pageSelection(' 1 - 5, 3 ',8).count,5);
  for(const value of ['0','9','1-9','-1','3-1','1,','1,,2','1.5','1–5','all,1','1e2','999999999999999999'])
    assert.ok(pageSelection(value,8).error,value);
});

test('built panel: native selection, confirmation, validation, defaults, background progress, cache confirmation and fallbacks',async()=>{
  const dom=new JSDOM('<!doctype html><html><head></head><body></body></html>',{url:'http://localhost/'});
  for(const key of ['window','document','HTMLElement','Node','MutationObserver'])globalThis[key]=dom.window[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT=true;
  const React=await import('react');
  const {render,fireEvent,waitFor,act,cleanup}=await import('@testing-library/react');
  let bundle;const require=createRequire(import.meta.url);
  dom.window.__ModuleLoader__={load:row=>{bundle=row.factory(require);}};
  vm.runInThisContext(await fs.readFile(new URL('../lib/client.js',import.meta.url),'utf8'));
  const store=bundle.createPanelState();store.set({sessionId:'s'});
  const requests=[];let tasks=[],outputDir='D:\\默认输出',pick={cancelled:false,path:'D:\\资料\\论文.pdf'},pickError=false,aiReview=false,created=0;
  const call=async r=>{
    requests.push(r);
    if(r.action==='status')return {tasks,outputDir,aiReview,configured:true,busy:tasks.some(t=>['running','stopping'].includes(t.status))};
    if(r.action==='pick'){if(pickError)throw Error('系统窗口不可用');return pick;}
    if(r.action==='inspect')return {path:r.pdf,pages:8,bytes:1024};
    if(r.action==='settings'){outputDir=r.outputDir??outputDir;aiReview=r.aiReview??aiReview;return {outputDir,aiReview,configured:true};}
    if(r.action==='start'){tasks=[{id:'job',args:r.args,status:'running',progress:{phase:'recognizing',completed:2,total:6}}];return {jobId:'job'};}
    if(r.action==='caches')return {entries:[{id:'0123456789abcdef',name:'论文.pdf',bytes:2048,busy:tasks.length>0}],cleaningDisabled:tasks.length>0};
    if(r.action==='prepareClear')return {id:r.identity,name:'论文.pdf',bytes:2048,token:'confirmed',message:'原 PDF 和导出成果会保留。'};
    if(r.action==='clear')return {cleared:true};
    throw Error('Unscripted action '+r.action);
  };
  const view=render(React.createElement(bundle.Panel,{store,call,ensureSession:async()=>{created++;await new Promise(r=>setTimeout(r,15));store.set({sessionId:'created'});return 'created';}}));
  const click=name=>fireEvent.click(view.getByRole('button',{name,exact:true}));
  const choose=async()=>{click('选择 PDF');await waitFor(()=>view.getByRole('dialog',{name:'确认翻译'}));};
  try{
    click('PDF 翻译');await act(async()=>{});
    assert.equal(view.container.querySelector('.pdf-entry').hidden,true);
    assert.equal(view.container.querySelectorAll('.pdf-actions button').length,3);
    assert.equal(view.getByRole('switch',{name:'AI 核验'}).checked,false);
    await choose();assert.equal(view.getByLabelText('翻译页码').value,'全部');
    assert.equal(requests.some(r=>r.action==='start'),false);
    click('取消');assert.equal(view.queryByRole('dialog'),null);
    pick={cancelled:true};click('选择 PDF');await act(async()=>{});
    assert.equal(view.queryByRole('dialog'),null);
    const settingsBefore=requests.filter(r=>r.action==='settings').length;
    click('选择输出目录');await act(async()=>{});
    assert.equal(requests.filter(r=>r.action==='settings').length,settingsBefore);
    pick={cancelled:false,path:'D:\\中文 输出'};click('选择输出目录');await waitFor(()=>view.getByText('输出目录已保存。'));
    assert.equal(outputDir,'D:\\中文 输出');
    pick={cancelled:false,path:'D:\\资料\\论文.pdf'};await choose();
    for(const value of ['0','9','3-1','1,,2']){
      fireEvent.change(view.getByLabelText('翻译页码'),{target:{value}});
      assert.equal(view.getByRole('button',{name:'开始翻译'}).disabled,true);
    }
    fireEvent.change(view.getByLabelText('翻译页码'),{target:{value:''}});
    assert.equal(view.getByRole('button',{name:'开始翻译'}).disabled,false);
    fireEvent.change(view.getByLabelText('翻译页码'),{target:{value:'1,3,5-8'}});
    click('开始翻译');await waitFor(()=>view.getByText('2/6 页'));
    assert.deepEqual(requests.find(r=>r.action==='start').args,{pdf:'D:\\资料\\论文.pdf',pages:'1,3,5,6,7,8',workers:4,imageQuality:'safe',thinking:'auto',outputDir:'D:\\中文 输出',aiReview:false});
    click('收起');assert.equal(view.container.querySelector('.pdf-entry').hidden,false);
    assert.equal(requests.some(r=>r.action==='cancel'),false);
    click('PDF 翻译 ·');await act(async()=>{});
    const picks=requests.filter(r=>r.action==='pick').length;
    click('选择 PDF');await act(async()=>{});
    assert.equal(requests.filter(r=>r.action==='pick').length,picks);
    click('清理缓存');await waitFor(()=>view.getByRole('button',{name:'清理该文档缓存'}));
    assert.equal(view.getByRole('button',{name:'清理该文档缓存'}).disabled,true);
    click('关闭窗口');
    tasks=[];click('收起');click('PDF 翻译 ·');await act(async()=>{});
    click('清理缓存');await waitFor(()=>assert.equal(view.getByRole('button',{name:'清理该文档缓存'}).disabled,false));
    click('清理该文档缓存');await waitFor(()=>view.getByRole('alertdialog'));
    assert.equal(requests.some(r=>r.action==='clear'),false);
    click('取消');assert.equal(requests.some(r=>r.action==='clear'),false);
    click('清理该文档缓存');await waitFor(()=>view.getByRole('alertdialog'));click('确认清理');
    await waitFor(()=>assert.equal(requests.filter(r=>r.action==='clear').length,1));
    assert.equal(requests.find(r=>r.action==='clear').token,'confirmed');
    await waitFor(()=>assert.equal(view.getByRole('button',{name:'关闭窗口'}).disabled,false));click('关闭窗口');
    pickError=true;click('选择 PDF');await waitFor(()=>view.getByRole('dialog',{name:'手动输入 PDF 路径'}));
    fireEvent.change(view.getByLabelText('PDF 绝对路径'),{target:{value:'D:\\手动\\文档.pdf'}});click('读取文档');
    await waitFor(()=>view.getByRole('dialog',{name:'确认翻译'}));assert.equal(view.getByLabelText('翻译页码').value,'全部');click('取消');
    pickError=false;await act(async()=>store.set({sessionId:null}));await choose();
    assert.equal(view.getByRole('button',{name:'开始翻译'}).disabled,false);click('取消');
    assert.equal(created,0);
    fireEvent.click(view.getByRole('switch',{name:'AI 核验'}));await waitFor(()=>assert.equal(aiReview,true));
    await choose();const before=requests.filter(r=>r.action==='start').length;
    click('开始翻译');click('开始翻译');await waitFor(()=>assert.equal(requests.filter(r=>r.action==='start').length,before+1));
    assert.equal(created,1);assert.equal(requests.filter(r=>r.action==='start').at(-1).sessionId,'created');
    assert.equal(tasks[0].args.aiReview,true);
    await waitFor(()=>assert.equal(view.getByRole('switch',{name:'AI 核验'}).disabled,false));
    fireEvent.click(view.getByRole('switch',{name:'AI 核验'}));await waitFor(()=>assert.equal(aiReview,false));
    assert.equal(tasks[0].args.aiReview,true);
  }finally{cleanup();dom.window.close();}
});
