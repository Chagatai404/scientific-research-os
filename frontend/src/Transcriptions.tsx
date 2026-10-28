import {useState} from 'react';
import {call,human} from './api';
import {useResource} from './hooks';
import {RichText} from './Document';
export function Transcriptions({record,source,path,revision}:{record:string;source:string;path:string;revision:string}){
 const drafts=useResource('transcriptions:'+record+':'+source,signal=>call<{id:string;path:string;revision:string;text:string;reviewed:boolean}[]>('transcription_list',{source},record,false,signal),record);
 const [text,setText]=useState(''),[by,setBy]=useState(''),[status,setStatus]=useState('');
 async function save(){try{await call('transcription_draft',{source,path,revision,text,by:by||'person'},record,true);setText('');drafts.retry();}catch(e){setStatus((e as Error).message);}}
 async function accept(draft:string){try{await human('transcription_accept',{draft,by},record);drafts.retry();}catch(e){setStatus((e as Error).message);}}
 return <details><summary>Faithful Transcription &amp; Review</summary><p>Keep the original scan visible. Preserve uncertain marks and apparent mistakes; a draft is not an endorsed mathematical correction.</p><label>Transcription Draft (LaTeX or Markdown)<textarea rows={6} value={text} onChange={e=>setText(e.target.value)}/></label><label>Reviewer Name<input value={by} onChange={e=>setBy(e.target.value)}/></label><button disabled={!text.trim()} onClick={save}>Save New Draft Revision</button>{status&&<p role="status">{status}</p>}{drafts.data?.filter(d=>d.path===path).map(d=><article key={d.id}><p>{d.reviewed?'Human Reviewed':'Draft'} · Source {d.revision.slice(0,12)}{d.revision!==revision?' · Earlier source revision':''}</p><RichText text={d.text} record={record}/><button onClick={()=>setText(d.text)}>Revise as New Draft</button><button disabled={!by||d.reviewed} onClick={()=>accept(d.id)}>Mark This Exact Draft Reviewed</button></article>)}</details>;
}
