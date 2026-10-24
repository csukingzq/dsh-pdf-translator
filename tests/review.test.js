import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {TranslatorManager} from '../src/manager.js';
import {CompletionGate} from '../src/completion-policy.js';
import {bindSessions} from '../src/session-binding.js';

const notice=id=>({source:{kind:'tool-jobs',form:'notice'},content:[{type:'text',text:`background job ${id} (pdf: sample.pdf) finished [status: completed]. Read its output with job_output.`}]});
const user={source:{kind:'user'},content:[{type:'text',text:'请再检查图表'}]};
test('session zip regression: only one job_output, no directory/MD/report reads; scoped to pure notices',()=>{
  const task={id:'pdf-cff42a6bbf104675',owner:'a',aiReview:false,status:'completed'};
  const gate=new CompletionGate({state:{tasks:[task]}}),agent={id:'a'};
  gate.admit(agent,1,[notice(task.id)]);
  const invoke=(name,args={})=>gate.guard({agent,name,arguments:args});
  assert.equal(invoke('job_output',{job_id:task.id}),undefined);
  for(const tool of ['pwsh','read','present','pdf_inspect','pdf_review','job_output'])assert.ok(invoke(tool,{job_id:task.id,jobId:task.id}),tool);
  assert.equal(gate.guard({agent:{id:'other'},name:'read'}),undefined);
  gate.inserted(agent,{source:{kind:'time-context',form:'snapshot'}});assert.ok(invoke('read'));
  gate.inserted(agent,user);assert.equal(invoke('read'),undefined);
  gate.admit(agent,2,[user,notice(task.id)]);assert.equal(invoke('pwsh'),undefined);
  gate.admit(agent,3,[notice('another-job'),notice(task.id)]);assert.equal(invoke('read'),undefined);
  gate.admit(agent,4,[{...notice(task.id),source:{kind:'user'}}]);assert.equal(invoke('read'),undefined);
  task.aiReview=true;gate.admit(agent,5,[notice(task.id)]);assert.equal(invoke('pdf_review',{jobId:task.id}),undefined);
  assert.ok(invoke('pdf_review',{jobId:'someone-else'}));
});

function sessionFixture(){
  let selection={},listeners=new Set(),created=0,resolve;
  const store={state:{},set(p){Object.assign(this.state,p);}};
  const navigation={selection:{getSnapshot:()=>selection,subscribe:fn=>{listeners.add(fn);return()=>listeners.delete(fn);}},openSession(id){selection={sessionId:id};for(const fn of listeners)fn();}};
  const sessions={list:{getSnapshot:()=>({phase:'ready',byId:{}})},create:async()=>{created++;return new Promise(r=>resolve=r);}};
  const workspaces={list:{getSnapshot:()=>({phase:'ready',items:[{workspaceId:'w',createdAt:'2026-10-24',sessionIds:[]}]})}};
  const binding=bindSessions(store,navigation,sessions,workspaces);
  return {store,navigation,binding,created:()=>created,resolve:id=>resolve(id)};
}
test('blank/existing/no session tracking, concurrent creation, and navigation during creation',async()=>{
  const f=sessionFixture();assert.equal(f.created(),0); // File selection/confirmation need not call ensure.
  f.navigation.openSession('blank');assert.equal(await f.binding.ensure(),'blank');assert.equal(f.created(),0);
  f.navigation.openSession('next');assert.equal(f.store.state.sessionId,'next');
  f.navigation.openSession(null);assert.equal(f.store.state.sessionId,null);
  const a=f.binding.ensure(),b=f.binding.ensure();assert.equal(f.created(),1);f.resolve('new');assert.equal(await a,'new');assert.equal(await b,'new');
  assert.equal(f.store.state.sessionId,'new');f.binding.dispose();
  const g=sessionFixture(),pending=g.binding.ensure();g.navigation.openSession('switched');g.resolve('orphan');
  await assert.rejects(pending,/切换/);assert.equal(g.store.state.sessionId,'switched');g.binding.dispose();
});

async function managerFixture(t){
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'pdf-review-test-'));
  let version='v0';
  const runner=async r=>{
    if(r.operation==='reviewRecover')return {};
    if(r.action==='apply'&&r.pages[0].fail)throw Error('compile failed');
    if(r.action==='apply'){version='v'+r.round;return {version,result:{output:'good.pdf'}};}
    return {version,pages:[{page:r.page||1}],totalPages:1};
  };
  const m=new TranslatorManager({get:()=>null},{dataDir:dir},runner);await m.ready;
  t.after(async()=>{await m.dispose();assert.ok(dir.startsWith(path.join(os.tmpdir(),'pdf-review-test-')));await fs.rm(dir,{force:true,recursive:true});});
  m.state.tasks.push({id:'pdf-test',owner:'a',aiReview:true,args:{pdf:'sample.pdf'},identity:'hash',status:'reviewing',result:{output:'good.pdf'},review:{status:'pending',rounds:0,version:null}});
  return m;
}
test('review authorization, version, two rounds, failed compile retention, finish idempotency',async t=>{
  const m=await managerFixture(t),task=m.state.tasks[0];
  const call=(action,extra={},owner='a')=>m.review.call({jobId:task.id,action,...extra},owner);
  await assert.rejects(call('inspect',{},'b'),/授权/);
  task.aiReview=false;await assert.rejects(call('inspect'),/未开启/);task.aiReview=true;
  await call('inspect');await assert.rejects(call('apply',{version:'old',pages:[{}]}),/版本/);
  await call('apply',{version:'v0',pages:[{}]});assert.equal(task.review.rounds,1);
  await assert.rejects(call('finish',{version:'v1',summary:'done'}),/复查/);
  await call('inspect');await assert.rejects(call('apply',{version:'v1',pages:[{fail:true}]}),/compile/);
  assert.equal(task.result.output,'good.pdf');assert.equal(task.review.rounds,2);
  await assert.rejects(call('apply',{version:'v1',pages:[{}]}),/上限/);
  await call('finish',{version:'v1',summary:'保留 PDF',remaining:['编译失败，第二轮未接受']});
  assert.equal(task.status,'completed');assert.equal(task.review.status,'finished');
  assert.equal((await call('finish')).review.status,'finished');
});
test('no-issue finish, persisted defaults/legacy config, cancel and restart',async t=>{
  const m=await managerFixture(t),task=m.state.tasks[0];
  assert.equal((await m.status('a')).aiReview,false);
  await m.settings({aiReview:true});assert.equal(task.aiReview,true);
  await m.settings({aiReview:false});assert.equal(task.aiReview,true);
  await m.review.call({jobId:task.id,action:'inspect'},'a');
  await m.review.call({jobId:task.id,action:'finish',version:'v0',summary:'逐页检查无新增问题'},'a');
  assert.equal(task.review.rounds,0);
  task.status='reviewing';task.review.status='pending';await m.review.cancel(task);
  assert.equal(task.review.status,'cancelled');assert.equal(task.result.output,'good.pdf');
  task.status='repairing';task.review.status='reviewing';delete m.state.aiReview;await m.persist();
  const restored=new TranslatorManager({get:()=>null},m.config,m.runner);await restored.ready;
  assert.equal(restored.state.aiReview,false);assert.equal(restored.state.tasks[0].review.status,'interrupted');await restored.dispose();
});

test('review apply is exclusive; cancellation retains PDF and cannot be resumed implicitly',async t=>{
  const m=await managerFixture(t),task=m.state.tasks[0];
  await m.review.call({jobId:task.id,action:'inspect'},'a');
  let entered;const running=new Promise(r=>entered=r);
  m.runner=async(r,_config,signal)=>{
    if(r.operation==='reviewRecover')return {};
    entered();return new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(Error('cancelled')),{once:true}));
  };
  const pending=m.review.call({jobId:task.id,action:'apply',version:'v0',pages:[{}]},'a');
  const rejected=assert.rejects(pending,/cancelled/);
  await running;
  await assert.rejects(m.review.call({jobId:task.id,action:'inspect'},'a'),/正在处理/);
  await m.cancel('a',task.id);await rejected;
  assert.equal(task.review.status,'cancelled');assert.equal(task.status,'completed');assert.equal(task.result.output,'good.pdf');
  await assert.rejects(m.review.call({jobId:task.id,action:'inspect'},'a'),/结束或中断/);
});
