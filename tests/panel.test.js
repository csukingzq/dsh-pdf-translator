import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { JSDOM } from 'jsdom';
import {Context,Service} from '@deepseek-ai/cordis';
import Registry from '@deepseek-ai/dsh-typert-registry';
import * as ClientRemote from '@deepseek-ai/dsh-api-gateway/client';

test('shipped apply runs in a plugin fiber and injects the mounted remote namespace',async()=>{
  const dom=new JSDOM('<!doctype html><html><head></head><body></body></html>',{url:'http://localhost/'});
  for(const key of ['window','document','HTMLElement','Node','MutationObserver'])globalThis[key]=dom.window[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT=true;
  const {act,waitFor}=await import('@testing-library/react');
  const require=createRequire(import.meta.url);let bundle;
  dom.window.__ModuleLoader__={load:row=>{bundle=row.factory(require);}};
  vm.runInThisContext(await fs.readFile(new URL('../lib/client.js',import.meta.url),'utf8'));
  const ctx=new Context(),requests=[];
  new class extends Service{
    constructor(){super(ctx,'connection');}
    interactions='none';
    rpc={open:()=>{},call:async(_base,endpoint,payload)=>{
      requests.push({endpoint,request:payload.args.request});
      return {ok:true,value:{tasks:[],outputDir:'D:/outputs',configured:true,busy:false}};
    }};
  };
  new class extends Service{
    constructor(){super(ctx,'slots');}
    inject(_name,callback){return callback();}
    register(){return()=>{};}
  };
  new class extends Service{constructor(){super(ctx,'uiWorkspace');} selection={getSnapshot:()=>({sessionId:'blank'}),subscribe:()=>()=>{}};};
  new class extends Service{constructor(){super(ctx,'sessions');}};
  new class extends Service{constructor(){super(ctx,'workspaces');}};
  try{
    await act(async()=>{ctx.plugin(Registry);ctx.plugin(ClientRemote);await new Promise(r=>setTimeout(r,25));ctx.plugin(bundle);await new Promise(r=>setTimeout(r,25));});
    await waitFor(()=>assert.ok(requests.some(r=>r.endpoint==='pdfTranslator/call'&&r.request.action==='status')));
    assert.equal(document.querySelector('[role=alert]'),null);
    assert.ok(document.querySelector('.pdf-entry'));
    assert.equal(document.querySelector('.pdf-panel').hidden,true);
  }finally{await act(async()=>{await ctx.fiber.dispose();});dom.window.close();}
});
