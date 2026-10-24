import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {pickNative} from '../src/native-picker.js';

function fake(){
  const child=new EventEmitter();child.stdout=new PassThrough();child.stderr=new PassThrough();child.kill=()=>{child.killed=true;};
  let args,options;
  return {child,get args(){return args;},get options(){return options;},spawnProcess:(_exe,a,o)=>{args=a;options=o;return child;}};
}
test('native picker transports Unicode paths as data, hides console and parses selection/cancellation',async()=>{
  const f=fake(),initial='D:\\中文 \' $() ` 输出';
  const result=pickNative('directory',initial,{...f,platform:'win32'});
  assert.equal(f.options.windowsHide,true);
  assert.equal(Buffer.from(f.args.at(-1),'base64').toString('utf8'),initial);
  assert.ok(f.args.includes('-STA'));
  const selected='D:\\中文 输出';f.child.stdout.write(JSON.stringify({cancelled:false,path:selected}));f.child.emit('close',0);
  assert.deepEqual(await result,{cancelled:false,path:selected});
  const c=fake(),cancel=pickNative('pdf','',{...c,platform:'win32'});
  c.child.stdout.write('{"cancelled":true}');c.child.emit('close',0);assert.deepEqual(await cancel,{cancelled:true});
});
test('native picker errors, timeout and disposal terminate the helper',async()=>{
  const f=fake(),controller=new AbortController(),p=pickNative('pdf','',{...f,platform:'win32',signal:controller.signal});
  controller.abort();await assert.rejects(p,/取消/);assert.equal(f.child.killed,true);
  const timeout=fake();await assert.rejects(pickNative('pdf','',{...timeout,platform:'win32',timeoutMs:5}),/超时/);assert.equal(timeout.child.killed,true);
  for(const body of ['garbage','{"cancelled":false,"path":"relative.pdf"}']){
    const bad=fake(),result=pickNative('pdf','',{...bad,platform:'win32'});bad.child.stdout.write(body);bad.child.emit('close',0);await assert.rejects(result,/选择结果/);
  }
});
