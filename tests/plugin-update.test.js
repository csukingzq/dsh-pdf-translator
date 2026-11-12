import test from 'node:test';
import assert from 'node:assert/strict';
import {checkPluginUpdate,startPluginUpdate,pollPluginUpdate,pluginName} from '../src/plugin-update.js';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {JSDOM} from 'jsdom';

test('market discovery, install and verification use the active profile and package',async t=>{
  const schema='dsh-market/update-api/v1';
  const calls=[];
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    calls.push([url,options]);
    const reply=[{features:{check:true,update:true,progress:true}},
      {package:{name:pluginName,installedVersion:'0.7.0',latestVersion:'0.8.0',updateAvailable:true}},
      {operation:{operationId:'run'}},
      {operation:{operationId:'run',packageName:pluginName,state:'running'}},
      {operation:{operationId:'run',packageName:pluginName,state:'succeeded',installedVersion:'0.7.0'}},
      {operation:{operationId:'run',packageName:pluginName,state:'succeeded',installedVersion:'0.8.0',outcome:{restartRequired:true}}}
    ][calls.length-1];
    return {ok:true,json:async()=>({schema,...reply})};
  });
  globalThis.document={baseURI:'https://test.invalid/dsh/'};
  try {
    assert.equal((await checkPluginUpdate(true)).installable,true);
    assert.equal(await startPluginUpdate(),'run');
    assert.equal(calls[2][0].pathname,'/dsh/dsh-market/api/v1/updates');
    assert.deepEqual(JSON.parse(calls[2][1].body),{packageName:pluginName});
    assert.equal(await pollPluginUpdate('run','0.8.0'),null);
    await assert.rejects(pollPluginUpdate('run','0.8.0'),/不符/);
    assert.match(await pollPluginUpdate('run','0.8.0'),/重启/);
  } finally {delete globalThis.document;}
});

test('shipped panel checks on open and installs only after a user click',async t=>{
  const dom=new JSDOM('<body></body>',{url:'https://test.invalid/dsh/'});
  for (const key of ['window','document','HTMLElement','Node','MutationObserver']) globalThis[key]=dom.window[key];
  globalThis.IS_REACT_ACT_ENVIRONMENT=true;
  const {render,fireEvent,waitFor}=await import('@testing-library/react');
  const React=await import('react');
  let bundle,posts=0;
  dom.window.__ModuleLoader__={load:row=>{bundle=row.factory(createRequire(import.meta.url));}};
  vm.runInThisContext(await fs.readFile(new URL('../lib/client.js',import.meta.url),'utf8'));
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    let value;
    if(url.pathname.endsWith('capabilities'))value={features:{check:true,update:true,progress:true}};
    else if(url.pathname.endsWith('operations'))value={operation:{operationId:'op',packageName:pluginName,state:'succeeded',installedVersion:'1.0.0',outcome:{restartRequired:true}}};
    else if(options.method==='POST'){posts++;value={operation:{operationId:'op'}};}
    else value={package:{name:pluginName,installedVersion:'0.8.0',latestVersion:'1.0.0',updateAvailable:true}};
    return {ok:true,json:async()=>({schema:'dsh-market/update-api/v1',...value})};
  });
  const store=bundle.createPanelState();
  const view=render(React.createElement(bundle.Panel,{store,call:async()=>({tasks:[],busy:false})}));
  try{
    fireEvent.click(view.getByRole('button',{name:'PDF 翻译'}));
    const update=await view.findByRole('button',{name:'更新插件'});
    assert.equal(posts,0);fireEvent.click(update);
    await waitFor(()=>assert.match(view.container.textContent,/已安装 1\.0\.0。请重启 DSH/));
    assert.equal(posts,1);
  }finally{view.unmount();dom.window.close();}
});
