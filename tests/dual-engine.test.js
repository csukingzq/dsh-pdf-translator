import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {existsSync} from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {TranslatorManager} from '../src/manager.js';
import {DualSetupController} from '../src/dual-setup.js';
import {runPython, root} from '../src/runner.js';

async function temporary(t){
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'dual-engine-'));
  t.after(async()=>{assert.ok(path.resolve(dir).startsWith(path.join(os.tmpdir(),'dual-engine-')));await fs.rm(dir,{recursive:true,force:true});});
  return dir;
}
const fixture=path.join(root,'tests/fixtures/vision-sample.pdf');
test('MinerU replaces the old OCR preference and cannot start AI review',async t=>{
  const dir=await temporary(t),calls=[];
  await fs.mkdir(path.join(dir,'work'));
  await fs.writeFile(path.join(dir,'work/plugin-state.json'),JSON.stringify({engine:'ocr',aiReview:true,outputDir:path.join(dir,'outputs'),tasks:[]}));
  const runner=async r=>{calls.push(r);return r.operation==='inspect'?{path:fixture,selected_pages:[1]}:{output:'mono.pdf',dual:'dual.pdf',mineru:'recognized.pdf'};};
  const setup={running:false,snapshot:()=>({ready:true}),cancel(){}};
  const manager=new TranslatorManager({get:()=>null},{dataDir:dir},runner,undefined,setup);
  t.after(()=>manager.dispose());await manager.ready;
  assert.equal(manager.state.engine,'mineru');assert.equal(manager.state.aiReview,false);
  await assert.rejects(manager.start({pdf:fixture,engine:'ocr'},'owner'));
  await assert.rejects(manager.start({pdf:fixture,engine:'mineru',aiReview:true},'owner'));
  await assert.rejects(manager.start({pdf:fixture,renderOnly:true},'owner'));
  const result=await manager.start({pdf:fixture,background:false},'owner');
  assert.equal(result.engine,'mineru');assert.equal(result.aiReview,false);
  assert.match(result.completionPolicy,/mineru/);
  assert.equal(manager.state.tasks.at(-1).status,'completed');
  assert.equal(calls.find(r=>r.operation==='translate').engine,'mineru');
});

test('both routes share text model edits and preserve old vision credentials',async t=>{
  const dir=await temporary(t),file=path.join(dir,'config.json');
  await fs.writeFile(file,JSON.stringify({base_url:'https://legacy.invalid',model:'vision',api_key:'legacy-secret',auto_repair_rounds:3,engines:{ocr:{api_key:'vision-secret'}}}));
  const setup=new DualSetupController({dataDir:dir},{probe:false});
  setup.saveConfig({engine:'pdf2zh',baseUrl:'https://text.invalid',model:'text',apiKey:'text-secret'});
  assert.equal(setup.snapshot('mineru').config.model,'text');
  setup.saveConfig({engine:'mineru',baseUrl:'https://text.invalid',model:'text-new'});
  const data=JSON.parse(await fs.readFile(file,'utf8'));
  assert.equal(data.model,'vision');assert.equal(data.auto_repair_rounds,3);
  assert.equal(data.engines.ocr.api_key,'vision-secret');assert.equal(data.engines.pdf2zh.api_key,'text-secret');
  assert.equal(setup.snapshot('mineru').config.model,'text-new');assert.equal(setup.snapshot('pdf2zh').config.model,'text-new');
  assert.doesNotMatch(JSON.stringify(setup.snapshots()),/secret/);
  assert.deepEqual(Object.keys(setup.snapshots()),['pdf2zh','mineru']);
});

test('MinerU setup also requires PDF2zh, and stale markers cannot hide a missing interpreter',async t=>{
  const dir=await temporary(t),setup=new DualSetupController({dataDir:dir},{probe:false});
  await fs.mkdir(path.join(dir,'runtime'));
  await fs.writeFile(path.join(dir,'runtime/mineru.json'),JSON.stringify({version:'4.2.3'}));
  assert.equal(setup.snapshot('mineru').runtimeReady,false);
  const python=path.join(dir,'.venv-mineru',process.platform==='win32'?'Scripts/python.exe':'bin/python');
  await fs.mkdir(path.dirname(python),{recursive:true});await fs.writeFile(python,'');
  assert.equal(setup.snapshot('mineru').runtimeReady,false);
});

test('cache confirmations isolate the two engines for the same document',async t=>{
  const dir=await temporary(t),calls=[],identity='a'.repeat(16);
  const runner=async r=>{calls.push(r);return r.operation==='cacheList'?{entries:[{id:identity,name:'cache',bytes:1}]}:{cleared:true};};
  const manager=new TranslatorManager({get:()=>null},{dataDir:dir},runner,undefined,{running:false,cancel(){}});
  t.after(()=>manager.dispose());
  const rows=(await manager.caches()).entries;assert.deepEqual(rows.map(r=>r.id),[identity,'ocr:'+identity]);
  const choice=await manager.prepareClear('ocr:'+identity);
  await manager.clear(choice.id,choice.token);
  assert.deepEqual(calls.at(-1),{operation:'cacheClear',engine:'ocr',identity});
  await assert.rejects(manager.clear(choice.id,choice.token),/过期/);
  const pdfChoice=await manager.prepareClear(identity);
  await manager.clear(identity,pdfChoice.token);
  assert.deepEqual(calls.at(-1),{operation:'cacheClear',engine:'pdf2zh',identity});
});

test('real Python subprocesses inspect with both isolated entry points',async()=>{
  for(const engine of ['pdf2zh','mineru','ocr']){
    const result=await runPython({operation:'inspect',engine,pdf:fixture,pages:'1'},{pythonPath:existsSync(path.join(root,'.venv/Scripts/python.exe'))?path.join(root,'.venv/Scripts/python.exe'):'python'});
    assert.equal(result.pages,1);assert.deepEqual(result.selected_pages,[1]);
  }
});
