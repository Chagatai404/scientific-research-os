import {useState} from 'react';
import {preference,savePreference} from './api';
import {RichText,safeUrl} from './Document';
export interface PreparedSegment {id:string;text:string;audio?:string;visual?:string}
export function MediaSequence({segments,visuals,base,record,identity}:{segments:PreparedSegment[];visuals:{path:string;caption?:string}[];base:string;record:string;identity:string}){
 const key='sequence:'+JSON.stringify([record,identity]);
 const [index,setIndex]=useState(()=>Math.max(0,Math.min(segments.length-1,Number(preference(key,'0'))||0))),[speed,setSpeed]=useState(()=>Number(preference(key+':speed','1'))||1);
 const current=segments[index];
 function choose(i:number){setIndex(i);savePreference(key,String(i));}
 if(!current)return <p>Text reading remains available while media preparation is incomplete.</p>;
 const visual=current.visual||visuals[Math.min(index,visuals.length-1)]?.path;
 return <section className="media-sequence"><nav aria-label="Narration Steps">{segments.map((seg,i)=><button key={seg.id} aria-current={index===i?'step':undefined} onClick={()=>choose(i)}>Step {i+1}</button>)}</nav><RichText text={current.text} base={base} record={record}/>{visual&&<figure><RichText text={'![Prepared derivation]('+visual+')'} base={base} record={record}/><figcaption>{visuals.find(v=>v.path===visual)?.caption||'Prepared visual for this narration step'}</figcaption></figure>}{current.audio&&<><audio key={current.id} aria-label="Prepared step narration" controls preload="metadata" src={safeUrl(base+current.audio,true,'',record)} onLoadedMetadata={e=>{e.currentTarget.playbackRate=speed;const time=Number(preference(key+':'+current.id,'0'));if(Number.isFinite(time)&&time>=0&&time<e.currentTarget.duration)e.currentTarget.currentTime=time;}} onTimeUpdate={e=>savePreference(key+':'+current.id,String(e.currentTarget.currentTime))} onEnded={()=>{if(index<segments.length-1)choose(index+1);}}/><label>Narration Speed<select value={speed} onChange={e=>{const next=Number(e.target.value);setSpeed(next);savePreference(key+':speed',String(next));const audio=e.currentTarget.closest('section')?.querySelector('audio');if(audio)audio.playbackRate=next;}}>{[.75,1,1.25,1.5,2].map(rate=><option key={rate} value={rate}>{rate}×</option>)}</select></label></>}<p className="muted">Step {index+1} of {segments.length}. Browsing or replay does not establish mastery.</p></section>;
}
