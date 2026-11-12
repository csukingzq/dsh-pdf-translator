import React, {useEffect,useRef,useState} from 'react';
import {checkPluginUpdate,currentVersion,startPluginUpdate,pollPluginUpdate} from './plugin-update.js';

const storageKey = 'dsh-pdf-translator.update-operation';
export function PluginUpdatePanel({visible,busy}) {
  const [info,setInfo] = useState(null), [message,setMessage] = useState('');
  const [pending,setPending] = useState(false);
  const [operation,setOperation] = useState(()=>{
    try {return JSON.parse(window.sessionStorage.getItem(storageKey));} catch {return null;}
  });
  const checked = useRef(false), lock = useRef(false);
  async function check(manual) {
    if (lock.current) return;
    lock.current=true;setPending(true);
    try {
      const state=await checkPluginUpdate(manual);
      setInfo(state);
      setMessage(state && !state.newer && manual?'已是最新版本。':'');
    } catch(e) {if(manual)setMessage(e.message);}
    finally {lock.current=false;setPending(false);}
  }
  useEffect(()=>{
    if(visible && !checked.current && !operation){checked.current=true;void check(false);}
  },[visible,operation]);
  useEffect(()=>{
    if(!operation)return;
    let alive=true,timer;
    async function poll(){
      try {
        const done=await pollPluginUpdate(operation.id,operation.target);
        if(!alive)return;
        if(!done){timer=setTimeout(poll,1500);return;}
        setInfo(null);setMessage(done);
      } catch(e){
        if(!alive)return;
        if(e instanceof TypeError || e.name==='TimeoutError'){
          setMessage('正在重新连接插件市场…');timer=setTimeout(poll,4000);return;
        }
        setMessage(e.message);
      }
      window.sessionStorage.removeItem(storageKey);setOperation(null);
    }
    void poll();
    return ()=>{alive=false;clearTimeout(timer);};
  },[operation]);
  async function install(){
    if(lock.current || busy || !info?.installable)return;
    lock.current=true;setPending(true);
    try{
      const id=await startPluginUpdate();
      const item={id,target:info.latest};
      window.sessionStorage.setItem(storageKey,JSON.stringify(item));setOperation(item);setMessage('');
    }catch(e){setMessage(e.message);}
    finally{lock.current=false;setPending(false);}
  }
  return <div>
    <div className="pdf-row"><small>插件 v{info?.installed||currentVersion}</small>
      <button disabled={pending||!!operation} onClick={()=>check(true)}>检查更新</button></div>
    {operation?<small role="status">正在更新到 {operation.target}…</small>:info?.newer&&
      <div className="pdf-row"><small>最新 v{info.latest}</small>{info.installable?
        <button disabled={busy||pending} onClick={install}>更新插件</button>:
        <a href={'https://github.com/csukingzq/dsh-pdf-translator/releases/tag/v'+info.latest} target="_blank" rel="noreferrer">下载新版安装包</a>}</div>}
    {message&&<small role="status">{message}</small>}
  </div>;
}
