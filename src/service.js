import { Remote, RemoteError, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol';
import { hostInfo, requestSchema } from './contract.js';

export class TranslatorService extends TypertRemoteService {
  static inject=['typert'];
  constructor(ctx, manager) {
    super(ctx,'pdfTranslator',{namespace:'pdfTranslator'});
    this.manager=manager;
    // Apply the standard stage-3 Remote initializer from plain JavaScript.
    Remote('call')(this.call,{name:'call',kind:'method',static:false,private:false,
      addInitializer:fn=>fn.call(this)});
    ctx.typert.register(hostInfo);
  }
  async call(input) {
    // This desktop management surface is user-only, never exposed as an AI tool.
    if(this.ctx.invocation?.peer.principal.kind!=='owner')
      throw new RemoteError('remote-access/denied','仅桌面用户可以使用翻译管理面板。',{});
    try {
      const r=requestSchema.parse(input), m=this.manager;
      switch(r.action){
        case 'status':return await m.status(r.sessionId);
        case 'inspect':return await m.inspect({pdf:r.pdf,pages:r.pages});
        case 'browse':return await m.browse(r.path,r.directories);
        case 'pick':return await m.pick(r.kind);
        case 'settings':return await m.settings(r);
        case 'caches':return await m.caches();
        case 'prepareClear':return await m.prepareClear(r.identity);
        case 'clear':return await m.clear(r.identity,r.token);
        case 'cancel':return await m.cancel(r.sessionId,r.jobId);
        case 'start':{
          const controller=this.ctx.get('sessionController');
          if(controller){const resolved=await controller.resolveAgent(r.sessionId);if(resolved.error)throw resolved.error;}
          return await m.start({...r.args,background:true},r.sessionId);
        }
        case 'open':{
          const state=await m.status(r.sessionId), task=state.tasks.find(t=>t.id===r.jobId);
          const target=task?.result?.[r.kind];if(!target)throw new Error('该任务还没有此成果。');
          const controller=this.ctx.get('sessionController');
          if(!controller)throw new Error('当前环境无法打开文件，请复制结果路径。');
          await controller.openWorkspacePath({path:target},new AbortController().signal);
          return {opened:true,path:target};
        }
      }
    }catch(e){throw new RemoteError('gateway/input-invalid',e.message,{});}
  }
}
