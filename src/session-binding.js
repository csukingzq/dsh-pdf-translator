// Workspace selection exists before the first message; header actions do not.
export function bindSessions(store, navigation, sessions, workspaces) {
  let revision=0, pending;
  const sync=()=>{revision++;store.set({sessionId:navigation.selection.getSnapshot().sessionId || null});};
  sync();
  const dispose=navigation.selection.subscribe(sync);
  async function ensure() {
    const selected=navigation.selection.getSnapshot().sessionId;
    if(selected)return selected;
    if(pending)return pending;
    const initial=revision;
    pending=(async()=>{
      const list=workspaces.list.getSnapshot();
      const catalog=sessions.list.getSnapshot();
      if(list.phase!=='ready'||catalog.phase!=='ready')throw Error('工作区正在加载，请稍后重试。');
      const ranked=list.items.map(w=>({w,time:Math.max(Date.parse(w.createdAt)||0,...w.sessionIds.map(id=>catalog.byId[id]?.updatedAt||0))})).sort((a,b)=>b.time-a.time);
      let workspaceId=ranked[0]?.w.workspaceId;
      if(!workspaceId)workspaceId=(await workspaces.initializeDefault(new AbortController().signal))?.workspaceId;
      if(!workspaceId)throw Error('无法建立工作区，请先打开工作区。');
      if(revision!==initial)throw Error('当前会话已切换，请重新开始翻译。');
      // Omitted preset uses Harness's current default; existing sessions are never recreated.
      const id=await sessions.create({workspaceId});
      if(revision!==initial)throw Error('会话建立期间发生切换，未启动翻译。');
      navigation.openSession(id);
      sync();
      return id;
    })().finally(()=>{pending=null;});
    return pending;
  }
  return {ensure,dispose};
}
