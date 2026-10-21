/* Consume trusted host-minted windows only. This module cannot mint freshness. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.ResearchOSAdviceFreshness=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function day(value){
    if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value)||value.slice(0,4)==='0000')return false;
    const d=new Date(value+'T00:00:00Z');
    return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===value;
  }
  function instant(value){
    if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value)||!day(value.slice(0,10)))return null;
    const d=new Date(value);
    return Number.isFinite(d.getTime())&&d.toISOString().replace('.000Z','Z')===value?d.getTime():null;
  }
  function validate(window,asOf){
    if(!window||typeof window!=='object'||Array.isArray(window)||Object.keys(window).sort().join(',')!=='day,end,start'||!day(asOf)||window.day!==asOf)return false;
    const start=instant(window.start),end=instant(window.end);
    return start!==null&&end!==null&&end>start&&end-start<=48*60*60*1000;
  }
  function isCurrent(window,asOf,now){
    const point=now===undefined||now===null?Date.now():now instanceof Date?now.getTime():instant(now);
    return point!==null&&Number.isFinite(point)&&validate(window,asOf)&&instant(window.start)<=point&&point<instant(window.end);
  }
  return {validate,isCurrent};
});
