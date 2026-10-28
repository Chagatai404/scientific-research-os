import {useEffect,useRef,useState} from 'react';
import {href} from './api';
export function CommandMenu({record}:{record:string}) {
  const dialog=useRef<HTMLDialogElement>(null),input=useRef<HTMLInputElement>(null),previous=useRef<HTMLElement|null>(null),[query,setQuery]=useState('');
  useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.isComposing)return;if((e.ctrlKey||e.metaKey)&&['k','p'].includes(e.key.toLowerCase())){e.preventDefault();previous.current=document.activeElement as HTMLElement;dialog.current?.showModal();setQuery(e.key.toLowerCase()==='p'?'Sources':'');input.current?.focus();}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[]);
  const commands=[['overview','Home'],['sessions','Sessions'],['learn','Learn'],['research','Research'],['sources','Sources'],['graph','Graph'],['activity','Activity'],['settings','Settings'],['tools','Research Tools']];
  return <dialog className="command-menu" ref={dialog} onClose={()=>previous.current?.focus()} aria-label="Commands & Search"><form method="dialog"><div className="section-title"><h2>Go To</h2><button aria-label="Close commands">×</button></div><label>Find a Command<input ref={input} value={query} onChange={e=>setQuery(e.target.value)}/></label><nav>{commands.filter(([,name])=>name.toLowerCase().includes(query.toLowerCase())).map(([view,name])=><a key={view} href={href(view,'',record)} onClick={()=>dialog.current?.close()}>{name}</a>)}</nav></form></dialog>;
}
