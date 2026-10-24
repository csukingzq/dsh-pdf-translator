// Validate before enabling Start; the Python bridge validates again at launch.
export function pageSelection(value,total){
  const text=value.trim();
  if(!text||text==='全部'||text.toLowerCase()==='all')return {pages:'all',count:total,error:''};
  const selected=new Set();
  for(const part of text.split(',')){
    const match=/^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$/.exec(part);
    if(!match)return {error:'页码格式错误，请填写 1-5 或 1,3,5-8。'};
    const start=Number(match[1]),end=Number(match[2]||match[1]);
    if(!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start<1||end>total||start>total)
      return {error:`页码超出范围，请填写 1–${total} 页。`};
    if(start>end)return {error:'起始页不能大于结束页。'};
    for(let i=start;i<=end;i++)selected.add(i);
  }
  return {pages:[...selected].sort((a,b)=>a-b).join(','),count:selected.size,error:''};
}
