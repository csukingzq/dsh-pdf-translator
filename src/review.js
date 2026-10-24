import {z} from 'zod';

export function completionPolicy(enabled){return enabled?
  '先用 pdf_review inspect 读取报告、逐页译文，按需 preview 原文/输出。发现内容或影响可读性的排版问题必须尝试 apply 修复（最多两轮），不能仅以重排差异为由搁置；apply.pages 提交完整替换页，apply.layout 可调整 figureMaxWidth（正文宽度比例）、figureMaxHeight（正文高度比例）或 fontSize（9–14pt）。每次后重新 inspect/preview；无问题即 finish 一次并附 PDF，达到上限或无法修复时说明剩余问题。不要直接改缓存、另起翻译或重复发送完成通知。':
  'AI 核验关闭。成功后只读取一次 job_output，直接简短回复“翻译完成”并附 output PDF 链接；已有警告仅简短提示。不要列目录、读取译文/报告、渲染预览或重新编译；不可声称内容核验通过。失败/取消如实报告。用户后续明确要求或本轮另有工作时可正常执行其他任务。';}

const schema=z.strictObject({jobId:z.string().min(1),action:z.enum(['inspect','preview','apply','finish']),
  version:z.string().optional(),page:z.number().int().positive().optional(),target:z.enum(['source','output']).optional(),
  pages:z.array(z.record(z.string(),z.json())).min(1).max(20).optional(),summary:z.string().max(2000).optional(),
  layout:z.strictObject({figureMaxWidth:z.number().min(.3).max(1).optional(),figureMaxHeight:z.number().min(.15).max(.65).optional(),fontSize:z.number().int().min(9).max(14).optional()}).optional(),
  remaining:z.array(z.string().max(1000)).max(50).optional()});

export class ReviewController {
  constructor(manager){this.m=manager;this.locks=new Set();this.controllers=new Map();}
  active(){return this.m.state.tasks.find(t=>['reviewing','repairing'].includes(t.status));}
  async cancel(task){
    task.review.status='cancelled';task.review.summary='AI 核验已取消，保留最近可用 PDF。';
    this.controllers.get(task.id)?.abort();
    if(!this.locks.has(task.id))task.status='completed';
    await this.m.persist();return {status:'cancelled',output:task.result.output};
  }
  async call(input,owner,exec={}){
    const a=schema.parse(input),m=this.m;await m.ready;
    const t=m.state.tasks.find(t=>t.id===a.jobId&&t.owner===owner);
    if(!owner||!t)throw Error('找不到当前会话授权的任务。');
    if(!t.aiReview||!t.result)throw Error('此任务未开启 AI 核验。');
    if(m.closed)throw Error('插件正在关闭。');
    if(this.locks.has(t.id))throw Error('该任务正在处理，请等待本次工具返回。');
    if(t.review.status==='finished'&&a.action==='finish')return {...t.result,review:t.review};
    if(!['pending','reviewing'].includes(t.review.status))throw Error('核验已结束或中断，最近可用 PDF 已保留。');
    if(a.action!=='inspect'&&(!a.version||a.version!==t.review.version))throw Error('文档版本不匹配，请重新 inspect。');
    if(a.action==='apply'&&t.review.rounds>=2)throw Error('已达到两轮修复上限，请 finish 并说明剩余问题。');
    if(a.action==='apply'&&!a.pages&&!Object.keys(a.layout||{}).length)throw Error('修订必须提交完整替换页 pages 或排版参数 layout。');
    if(a.action==='finish'&&!a.summary?.trim())throw Error('请填写核验结论 summary。');
    if(a.action==='finish'&&(t.review.needsRecheck||!t.review.total||t.review.seen?.length<t.review.total)&&!a.remaining?.length)throw Error('尚未逐页复查，请继续 inspect；若无法完成，remaining 必须说明未完成的核验。');
    if(a.action==='finish'&&t.review.lastError&&!a.remaining?.length)throw Error('上次修复未成功，请在 remaining 说明剩余问题。');
    this.locks.add(t.id);const controller=new AbortController();this.controllers.set(t.id,controller);m.controllers.add(controller);
    const pending=(async()=>{
      try{
        if(a.action==='apply'){t.review.rounds++;t.status='repairing';}
        t.review.status='reviewing';await m.persist();
        const value=await m.runner({operation:'review',action:a.action,result:t.result,pdf:t.args.pdf,identity:t.identity,
          expectedVersion:a.version,page:a.page,target:a.target,pages:a.pages,layout:a.layout,summary:a.summary,remaining:a.remaining||[],round:t.review.rounds},
          m.config,exec.signal?AbortSignal.any([exec.signal,controller.signal]):controller.signal);
        t.review.version=value.version;
        if(value.result)t.result={...t.result,...value.result};
        if(a.action==='apply'){t.review.lastError=null;t.review.needsRecheck=true;t.review.seen=[];}
        if(a.action==='inspect'){
          t.review.seen=[...new Set([...(t.review.seen||[]),...(value.pages||[]).map(p=>p.page)])];
          t.review.total=value.totalPages;
          if(t.review.seen.length>=value.totalPages)t.review.needsRecheck=false;
        }
        if(a.action==='finish'){t.review={...t.review,status:'finished',summary:a.summary,remaining:a.remaining||[],finishedAt:Date.now()};t.status='completed';}
        return {...value,jobId:t.id,rounds:t.review.rounds,roundsRemaining:2-t.review.rounds,review:t.review,output:t.result.output};
      }catch(e){t.review.lastError=e.message;
        if(a.action==='apply'){
          try{await m.runner({operation:'reviewRecover'},m.config);}
          catch(recovery){m.closed=true;t.review.status='interrupted';t.review.lastError=`${e.message}；恢复未完成：${recovery.message}。请释放被占用文件后重启 Harness。`;throw Error(t.review.lastError);}
        }
        if((controller.signal.aborted||exec.signal?.aborted)&&t.review.status!=='cancelled'){t.review.status='interrupted';t.review.summary='核验中断，保留最近可用 PDF。';}
        throw e;
      }finally{
        t.status=['pending','reviewing'].includes(t.review.status)?'reviewing':'completed';
        this.locks.delete(t.id);this.controllers.delete(t.id);m.controllers.delete(controller);await m.persist();
      }
    })();
    this.pending=pending.catch(()=>{});return pending;
  }
}
