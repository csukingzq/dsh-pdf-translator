import {completionPolicy} from './review.js';

// Only plugin-owned native job notices can arm this guard. User text never can.
export class CompletionGate {
  constructor(manager){this.manager=manager;this.turns=new Map();}
  match(message,owner){
    if(message.source?.kind!=='tool-jobs'||message.source?.form!=='notice')return null;
    const text=(message.content||[]).filter(b=>b.type==='text').map(b=>b.text).join('\n');
    const id=/^background job ([\w-]+)(?:\s|$)/.exec(text)?.[1];
    return this.manager.state.tasks.find(t=>t.id===id&&t.owner===owner)||null;
  }
  admit(agent,turn,messages){
    let state=this.turns.get(agent.id);
    if(state?.turn!==turn){state={turn,pure:true,tasks:new Map(),read:new Set()};this.turns.set(agent.id,state);}
    for(const message of messages){const task=this.match(message,agent.id);if(task)state.tasks.set(task.id,task);else if(!this.passive(message))state.pure=false;}
    return state;
  }
  passive(message){return (message.source?.kind==='runtime-context'||message.source?.kind==='time-context')&&message.source?.form==='snapshot'||message.source?.kind==='skill-catalog'&&message.source?.form==='catalog';}
  inserted(agent,message){if(!this.match(message,agent.id)&&!this.passive(message)){const state=this.turns.get(agent.id);if(state)state.pure=false;}}
  guard(exec){
    const state=this.turns.get(exec.agent?.id);
    if(!state?.pure||!state.tasks.size)return;
    const a=exec.arguments||{};
    // PTC's inner calls still pass this same guard.
    if(exec.name==='run_code')return;
    if(exec.name==='job_output'&&state.tasks.has(a.job_id)&&!state.read.has(a.job_id)){
      state.read.add(a.job_id);return;
    }
    if(exec.name==='pdf_review'&&state.tasks.get(a.jobId)?.aiReview)return;
    // A Markdown PDF link requires no presentation/file tool.
    return '本轮仅由 PDF 完成通知触发。每个任务只读取一次 job_output；核验开启时用 pdf_review，否则直接简短回复并附结果中的 PDF 链接。用户新要求和包含其他工作的轮次不受此限制。';
  }
  prompt(owner){
    const state=this.turns.get(owner);
    if(!state?.tasks.size)return '';
    return [...state.tasks.values()].map(t=>`PDF 任务 ${t.id} 的核验设置：${completionPolicy(t.aiReview)}${t.status==='failed'||t.status==='killed'?' 此任务未成功，不得报告翻译完成。':''}`).join('\n');
  }
}

export function installCompletionPolicy(ctx,manager){
  const gate=new CompletionGate(manager),bound=new Set(),disposers=[];
  ctx.effect(()=>()=>{for(const dispose of disposers)dispose();});
  ctx.tools.guard(exec=>gate.guard(exec));
  ctx.on('agent/pre-step',async({agent,turn,messages},next)=>{
    const state=gate.admit(agent,turn,messages);
    if(state.tasks.size&&!bound.has(agent)){
      bound.add(agent);
      const prompt=agent.ctx?.get('systemPrompt');
      if(prompt)disposers.push(prompt.section({name:'pdf-completion:'+agent.id,order:9999,interpolate:false,text:({scope})=>scope===agent?gate.prompt(agent.id):''}));
    }
    const decision=await next();
    if(decision.kind==='enter')gate.admit(agent,turn,decision.messages);
    else gate.turns.delete(agent.id);
    return decision;
  });
  ctx.on('agent/inbox/inserted',({agent,message})=>gate.inserted(agent,message));
  ctx.on('agent/turn-stopping',async({agent})=>{
    const state=gate.turns.get(agent.id);
    for(const task of state?.tasks.values()||[]){
      if(task.aiReview&&['reviewing','repairing'].includes(task.status)&&!manager.review.locks.has(task.id)){
        task.review.status='interrupted';task.review.summary='对话已结束但未完成核验，保留最近可用 PDF。';task.status='completed';await manager.persist();
      }
    }
    gate.turns.delete(agent.id);
  });
  return gate;
}
