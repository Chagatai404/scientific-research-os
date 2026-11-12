import {useRef,useState} from 'react';
import {preference,savePreference} from './api';
import {RichText,safeUrl} from './Document';
export interface PreparedAnimation {video?:string;poster?:string;keyframes?:string;basis?:string;looked_at?:boolean;pauses?:{at:number|'end';note:string}[]}
export interface MediaState {state: string; note?: string}
export interface CodeExample {path?: string; language?: string; state: string; executed?: boolean; verified_by_research_os?: boolean; note?: string; execution?: {ran_at?: string; runtime?: string; exit_code?: number; ran_by?: string}}
/** What can be shown for a part right now. A missing engine is a state to report, never a reason to hide the text. */
export interface MediaReadiness {text?: MediaState; 'static-visual'?: MediaState; 'narration-audio'?: MediaState; animation?: MediaState; code?: MediaState & {examples?: CodeExample[]}}
const NOT_SHOWN = new Set(['not-rendered', 'not-spoken', 'missing', 'unchecked']);
/** One honest line for every medium that is planned but cannot be shown yet; empty when nothing is missing. */
export function readinessLines(readiness?: MediaReadiness): string[] {
  if (!readiness) return [];
  const names: [keyof MediaReadiness, string][] = [['static-visual', 'Figure'], ['narration-audio', 'Narration audio'], ['animation', 'Animation']];
  return names.flatMap(([key, label]) => {const entry = readiness[key] as MediaState | undefined; return entry && NOT_SHOWN.has(entry.state) ? [`${label}: ${entry.note || entry.state.replace('-', ' ')}. The text carries the idea.`] : [];});
}
/** Code is shown with what is known about running it: read-only unless an execution was recorded for exactly this code. */
export function codeProvenance(example: CodeExample): string {
  if (example.state === 'run-recorded' && example.execution) return `Run recorded: ${example.execution.ran_by || 'unknown'} on ${example.execution.ran_at || 'an unknown date'} (${example.execution.runtime || 'unknown runtime'}), exit code ${example.execution.exit_code}. Reported, not re-run by Research OS.`;
  if (example.state === 'not-run') return 'Not run: shown as code to read. No execution was recorded.';
  if (example.state === 'changed') return 'The code changed after it was recorded; any recorded run is for the old code.';
  if (example.state === 'missing') return 'The code file is not available.';
  return example.note || 'Execution is not established.';
}
export interface PreparedClip {url?:string;start:number;end:number;transcript_verified?:boolean;title?:string}
export function clipEmbed(clip:PreparedClip){
 if(!clip.transcript_verified||!Number.isFinite(clip.start)||!Number.isFinite(clip.end)||clip.start<0||clip.end<=clip.start||clip.end-clip.start>180)return null;
 try{const url=new URL(clip.url||'');const id=url.hostname==='youtu.be'?url.pathname.slice(1):['www.youtube.com','youtube.com','www.youtube-nocookie.com'].includes(url.hostname)?url.searchParams.get('v')||url.pathname.split('/').pop():null;if(!id||!/[A-Za-z0-9_-]{11}/.test(id)||id.length!==11)return null;return 'https://www.youtube-nocookie.com/embed/'+id+'?start='+Math.floor(clip.start)+'&end='+Math.ceil(clip.end)+'&rel=0';}catch{return null;}
}
export function MediaArtifacts({animation,clip,base,record,readiness}:{animation?:PreparedAnimation;clip?:PreparedClip;base:string;record:string;readiness?:MediaReadiness}){
 const [loaded,setLoaded]=useState(false),[note,setNote]=useState('');const passed=useRef(new Set<number>());const embed=clip&&clipEmbed(clip);
 const key='animation:'+JSON.stringify([record,base,animation?.video]);
 const lines=readinessLines(readiness),examples=readiness?.code?.examples||[];
 return <>{lines.length>0&&<ul className="media-readiness" role="status">{lines.map(line=><li key={line}>{line}</li>)}</ul>}{examples.length>0&&<section><h3>Code Example</h3>{examples.map(e=><p key={e.path}><code>{e.path}</code> ({e.language||'code'}) · {codeProvenance(e)}</p>)}</section>}{animation?.video&&<section><h3>Prepared Animation</h3>{animation.basis&&<p>Basis: {animation.basis}</p>}<video controls preload="none" style={{maxWidth:'100%'}} src={safeUrl(base+animation.video,true,'',record)} poster={animation.poster?safeUrl(base+animation.poster,true,'',record):undefined} onLoadedMetadata={e=>{const value=Number(preference(key,'0'));if(value>=0&&value<e.currentTarget.duration)e.currentTarget.currentTime=value;}} onTimeUpdate={e=>{const time=e.currentTarget.currentTime;savePreference(key,String(time));animation.pauses?.forEach((pause,i)=>{if(typeof pause.at==='number'&&time>=pause.at&&!passed.current.has(i)){passed.current.add(i);e.currentTarget.pause();setNote(pause.note);}});}} onEnded={()=>setNote(animation.pauses?.find(p=>p.at==='end')?.note||'Replay or inspect the key frames.')} />{note&&<p role="status">{note}</p>}{animation.keyframes&&<RichText text={'![Animation key frames]('+animation.keyframes+')'} base={base} record={record}/>}</section>}{clip&&<section><h3>{clip.title||'Verified Video Segment'}</h3>{embed?<>{loaded?<iframe title={clip.title||'Verified teaching clip'} src={embed} sandbox="allow-scripts allow-presentation" allow="fullscreen" referrerPolicy="no-referrer" style={{width:'100%',aspectRatio:'16 / 9',border:0}}/>:<button onClick={()=>setLoaded(true)}>Load Verified Clip ({Math.ceil(clip.end-clip.start)} Seconds)</button>}<p className="muted">Loading contacts YouTube. The verified transcript segment is bounded to the selected interval.</p></>:<p>Clip playback is unavailable until its transcript and bounded interval are verified.</p>}</section>}</>;
}
