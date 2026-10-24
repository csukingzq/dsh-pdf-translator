import {useLayoutEffect,useRef,useState} from 'react';

// Positions are UI preferences only; denied browser storage must not block translation.
export function useFloatingPosition(name,visible=true,anchor){
  const ref=useRef(null),drag=useRef(null),moved=useRef(false);
  const key=`pdf-translator.position.${name}`;
  const [position,setPosition]=useState(()=>{
    try{const p=JSON.parse(window.localStorage.getItem(key));
      if(Number.isFinite(p?.x)&&Number.isFinite(p?.y))return p;
    }catch{}
    return null;
  });
  const current=useRef(position);
  function clamp(p){
    const box=ref.current.getBoundingClientRect();
    const top=Math.max(12,(parseFloat(window.getComputedStyle(document.documentElement).getPropertyValue('--dsh-frame-top-clearance'))||40)+8);
    return {x:Math.max(12,Math.min(p.x,window.innerWidth-box.width-12)),
      y:Math.max(top,Math.min(p.y,window.innerHeight-box.height-12))};
  }
  function update(p){const next=clamp(p);current.current=next;
    setPosition(prev=>prev?.x===next.x&&prev?.y===next.y?prev:next);return next;}
  function save(p){try{window.localStorage.setItem(key,JSON.stringify(p));}catch{}}
  useLayoutEffect(()=>{
    if(!visible)return;
    if(anchor)current.current=anchor();
    const fit=()=>{if(drag.current)return;const box=ref.current.getBoundingClientRect();update(current.current||{x:box.left,y:box.top});};
    fit();window.addEventListener('resize',fit);
    const observer=typeof ResizeObserver==='function'?new ResizeObserver(fit):null;
    observer?.observe(ref.current);
    return()=>{window.removeEventListener('resize',fit);observer?.disconnect();};
  },[visible]);
  const handle={
    onPointerDown(e){
      moved.current=false;
      if(e.button!==0||e.target.closest('button,input,select,a')&&e.target.closest('button,input,select,a')!==e.currentTarget)return;
      const box=ref.current.getBoundingClientRect();
      drag.current={id:e.pointerId,x:e.clientX,y:e.clientY,left:box.left,top:box.top};
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    onPointerMove(e){const d=drag.current;if(!d||d.id!==e.pointerId)return;
      const dx=e.clientX-d.x,dy=e.clientY-d.y;
      if(!moved.current&&Math.hypot(dx,dy)<5)return;
      moved.current=true;update({x:d.left+dx,y:d.top+dy});
    },
    onPointerUp(e){if(drag.current?.id!==e.pointerId)return;
      drag.current=null;if(moved.current)save(current.current);
      e.currentTarget.releasePointerCapture(e.pointerId);
    },
    onPointerCancel(){drag.current=null;moved.current=false;},
    onLostPointerCapture(){drag.current=null;},
    onClickCapture(e){if(moved.current&&e.detail!==0){moved.current=false;e.preventDefault();e.stopPropagation();}},
    onKeyDown(e){
      if(e.target!==e.currentTarget)return;
      const delta={ArrowLeft:[-16,0],ArrowRight:[16,0],ArrowUp:[0,-16],ArrowDown:[0,16]}[e.key];
      if(!delta)return;e.preventDefault();
      const box=ref.current.getBoundingClientRect();save(update({x:box.left+delta[0],y:box.top+delta[1]}));
    },
  };
  return {ref,style:position?{left:position.x,top:position.y,right:'auto',bottom:'auto'}:undefined,handle,
    getPosition:()=>current.current||{x:20,y:window.innerHeight-60}};
}
