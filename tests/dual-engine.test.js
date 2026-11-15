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
test('engine selection routes work and only OCR can enter review, including legacy preference',async t=>{
  const dir=await temporary(t),calls=[];
  const runner=async r=>{
    calls.push(r);
    if(r.operation==='inspect')return {path:fixture,selected_pages:[1]};
    if(r.operation==='translate')return r.engine==='ocr'?{output:'ocr.pdf',project:'source.zip'}:{output:'mono.pdf',dual:'dual.pdf'};
  };
  const setup={running:false,snapshot:()=>({ready:true}),cancel(){}};
  const manager=new TranslatorManager({get:()=>null},{dataDir:dir},runner,undefined,setup);
  t.after(()=>manager.dispose());
  await manager.settings({aiReview:true});
  const pdf=await manager.start({pdf:fixture,background:false},'owner');
  assert.equal(pdf.engine,'pdf2zh');assert.equal(pdf.aiReview,false);assert.match(pdf.completionPolicy,/dual/);
  await assert.rejects(manager.start({pdf:fixture,engine:'pdf2zh',aiReview:true},'owner'),/仅适用于 OCR/);
  await assert.rejects(manager.start({pdf:fixture,engine:'pdf2zh',renderOnly:true},'owner'),/仅适用于 OCR/);
  const task=manager.state.tasks[0];task.aiReview=true;
  await assert.rejects(manager.review.call({jobId:task.id,action:'inspect'},'owner'),/仅 OCR/);
  await manager.settings({engine:'ocr'});
  const ocr=await manager.start({pdf:fixture,background:false},'owner');
  assert.equal(ocr.engine,'ocr');assert.equal(ocr.aiReview,true);assert.match(ocr.completionPolicy,/pdf_review/);
  assert.equal(manager.state.tasks.at(-1).status,'reviewing');
  assert.deepEqual(calls.filter(r=>r.operation==='translate').map(r=>r.engine),['pdf2zh','ocr']);
});

test('per-engine model edits preserve legacy settings, both keys and unknown options without exposing secrets',async t=>{
  const dir=await temporary(t),file=path.join(dir,'config.json');
  await fs.writeFile(file,JSON.stringify({base_url:'https://legacy.invalid',model:'vision',api_key:'legacy-secret',auto_repair_rounds:3}));
  const setup=new DualSetupController({dataDir:dir},{probe:false});
  assert.equal(setup.snapshot('ocr').config.model,'vision');
  setup.saveConfig({engine:'pdf2zh',baseUrl:'https://text.invalid',model:'text',apiKey:'text-secret'});
  setup.saveConfig({engine:'ocr',baseUrl:'https://vision.invalid',model:'vision-new'});
  setup.saveConfig({engine:'pdf2zh',baseUrl:'https://text.invalid',model:'text-new'});
  const data=JSON.parse(await fs.readFile(file,'utf8'));
  assert.equal(data.model,'vision');assert.equal(data.auto_repair_rounds,3);
  assert.equal(data.engines.ocr.api_key,'legacy-secret');assert.equal(data.engines.pdf2zh.api_key,'text-secret');
  assert.equal(setup.snapshot('ocr').config.model,'vision-new');assert.equal(setup.snapshot('pdf2zh').config.model,'text-new');
  assert.doesNotMatch(JSON.stringify(setup.snapshots()),/secret/);
});

test('cache confirmations route OCR document caches separately from shared layout caches',async t=>{
  const dir=await temporary(t),calls=[],identity='a'.repeat(16);
  const runner=async r=>{calls.push(r);return r.operation==='cacheList'?{entries:[{id:r.engine==='ocr'?identity:'engine',name:'cache',bytes:1}]}:{cleared:true};};
  const manager=new TranslatorManager({get:()=>null},{dataDir:dir},runner,undefined,{running:false,cancel(){}});
  t.after(()=>manager.dispose());
  const rows=(await manager.caches()).entries;assert.deepEqual(rows.map(r=>r.id),['engine','ocr:'+identity]);
  const choice=await manager.prepareClear('ocr:'+identity);
  await manager.clear(choice.id,choice.token);
  assert.deepEqual(calls.at(-1),{operation:'cacheClear',engine:'ocr',identity});
  await assert.rejects(manager.clear(choice.id,choice.token),/过期/);
});

test('real Python subprocesses inspect with both isolated entry points',async()=>{
  for(const engine of ['pdf2zh','ocr']){
    const result=await runPython({operation:'inspect',engine,pdf:fixture,pages:'1'},{pythonPath:existsSync(path.join(root,'.venv/Scripts/python.exe'))?path.join(root,'.venv/Scripts/python.exe'):'python'});
    assert.equal(result.pages,1);assert.deepEqual(result.selected_pages,[1]);
  }
});
