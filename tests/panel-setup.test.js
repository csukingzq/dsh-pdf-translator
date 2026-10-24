import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {JSDOM} from 'jsdom';

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function baseSetup(patch={}){
  return {ready:false,running:false,platform:'win32',platformOk:true,phase:'idle',message:'',error:'',configError:'',elapsedSeconds:0,log:[],
    missing:{python:true,runtime:true,config:true,model:true},config:{baseUrl:'',model:'',hasApiKey:false},...patch};
}
async function mount(){
  const dom=new JSDOM('<!doctype html><html><head></head><body></body></html>',{url:'http://localhost/'});
  for(const key of ['window','document','HTMLElement','Node','MutationObserver'])globalThis[key]=dom.window[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT=true;
  const React=await import('react');
  const {render,fireEvent,waitFor,act,cleanup}=await import('@testing-library/react');
  let bundle;const require=createRequire(import.meta.url);
  dom.window.__ModuleLoader__={load:row=>{bundle=row.factory(require);}};
  vm.runInThisContext(await fs.readFile(new URL('../lib/client.js',import.meta.url),'utf8'));
  const store=bundle.createPanelState();store.set({sessionId:'s',visible:true});
  return {dom,React,render,fireEvent,waitFor,act,cleanup,bundle,store};
}

test('first-run panel installs the environment and shows progress',async()=>{
  const {dom,React,render,fireEvent,waitFor,act,cleanup,bundle,store}=await mount();
  let setup=baseSetup();
  const requests=[];
  const call=async r=>{
    requests.push(r);
    if(r.action==='status')return {tasks:[],outputDir:'D:\\输出',aiReview:false,configured:true,setup,busy:setup.running};
    if(r.action==='setupStart'){setup=baseSetup({running:true,phase:'tectonic',message:'下载 Tectonic…'});return setup;}
    if(r.action==='setupCancel'){setup=baseSetup({message:'已取消环境准备。',phase:'cancelled'});return setup;}
    if(r.action==='pick')return {cancelled:false,path:'D:\\资料\\论文.pdf'};
    if(r.action==='inspect')return {path:r.pdf,pages:3,bytes:1024};
    if(r.action==='settings')return {outputDir:'D:\\输出',aiReview:false,configured:true};
    throw Error('Unscripted action '+r.action);
  };
  const view=render(React.createElement(bundle.Panel,{store,call,ensureSession:async()=>'s'}));
  const click=name=>fireEvent.click(view.getByRole('button',{name,exact:true}));
  try{
    await waitFor(()=>view.getByText('首次使用需要准备运行环境'));
    assert.ok(view.getByText(/约 300 MB/));
    click('选择 PDF');await waitFor(()=>view.getByRole('dialog',{name:'确认翻译'}));
    assert.equal(view.getByRole('button',{name:'开始翻译'}).disabled,true);
    assert.ok(view.getByText('请先完成运行环境准备和模型配置。'));
    click('取消');
    click('一键准备环境');await waitFor(()=>view.getByText('正在准备运行环境…'));
    assert.ok(requests.some(r=>r.action==='setupStart'));
    assert.ok(view.getByText(/下载 Tectonic/));
    await waitFor(()=>view.getByRole('button',{name:'取消'}),{timeout:2000});
    click('取消');await waitFor(()=>assert.equal(requests.filter(r=>r.action==='setupCancel').length,1));
    setup=baseSetup({ready:true,running:false,phase:'done',missing:{python:false,runtime:false,config:false,model:false},
      config:{baseUrl:'https://api.example.com/v1',model:'vision',hasApiKey:true}});
    await act(async()=>{await sleep(1200);});
    await waitFor(()=>assert.equal(view.queryByText('首次使用需要准备运行环境'),null),{timeout:2500});
  }finally{cleanup();dom.window.close();}
});

test('model config dialog saves without exposing the stored key',async()=>{
  const {dom,React,render,fireEvent,waitFor,cleanup,bundle,store}=await mount();
  let setup=baseSetup({missing:{python:false,runtime:false,config:true,model:true}});
  const requests=[];
  const call=async r=>{
    requests.push(r);
    if(r.action==='status')return {tasks:[],outputDir:'D:\\输出',aiReview:false,configured:true,setup,busy:false};
    if(r.action==='saveConfig'){
      setup=baseSetup({ready:true,missing:{python:false,runtime:false,config:false,model:false},
        config:{baseUrl:r.baseUrl,model:r.model,hasApiKey:true}});
      return setup.config;
    }
    throw Error('Unscripted action '+r.action);
  };
  const view=render(React.createElement(bundle.Panel,{store,call,ensureSession:async()=>'s'}));
  try{
    await waitFor(()=>view.getByText('还差模型配置'));
    fireEvent.click(view.getByRole('button',{name:'填写模型配置'}));
    await waitFor(()=>view.getByRole('dialog',{name:'模型配置'}));
    const key=view.getByLabelText('API 密钥');
    assert.equal(key.type,'password');
    assert.equal(key.value,'');
    assert.equal(view.getByLabelText('接口地址').value,'https://api.deepseek.com/v1');
    fireEvent.change(view.getByLabelText('接口地址'),{target:{value:'https://api.example.com/v1'}});
    fireEvent.change(view.getByLabelText('模型名称'),{target:{value:'vision-model'}});
    fireEvent.change(key,{target:{value:'secret-key'}});
    fireEvent.click(view.getByRole('button',{name:'保存'}));
    await waitFor(()=>assert.equal(requests.filter(r=>r.action==='saveConfig').length,1));
    const sent=requests.find(r=>r.action==='saveConfig');
    assert.deepEqual({baseUrl:sent.baseUrl,model:sent.model,apiKey:sent.apiKey},
      {baseUrl:'https://api.example.com/v1',model:'vision-model',apiKey:'secret-key'});
    await waitFor(()=>view.getByText('模型配置已保存。'));
    await waitFor(()=>assert.equal(view.queryByText('还差模型配置'),null));
    assert.equal(view.queryByDisplayValue('secret-key'),null);
  }finally{cleanup();dom.window.close();}
});
