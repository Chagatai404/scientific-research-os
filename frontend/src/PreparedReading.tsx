import {useState} from 'react';
import {call,preference,savePreference} from './api';
import {MediaSequence,type PreparedSegment} from './MediaSequence';
import {MediaArtifacts,type PreparedAnimation,type PreparedClip} from './MediaArtifacts';
interface Reading {title:string;base:string;sections:{id:string;title:string;animation?:PreparedAnimation;clip?:PreparedClip;segments:PreparedSegment[];visuals:{path:string;caption?:string}[]}[]}
export function PreparedReading({record,lesson,item}:{record:string;lesson:string;item?:string}) {
  const key='reading:'+JSON.stringify([record,lesson]);
  const [reading,setReading]=useState<Reading|null>(null),[section,setSection]=useState(()=>Number(preference(key,'0'))||0),[error,setError]=useState('');
  async function open(){try{setReading(await call<Reading>('workspace_lesson_material',{lesson,...(item?{item}:{})},record,true));}catch(e){setError((e as Error).message);}}
  return <details className="prepared-reading"><summary>Prepared Reading &amp; Narration</summary>{!reading?<><p>Browse prepared stages freely. Reading during an assessment is recorded as assistance.</p><button onClick={open}>Open Prepared Reading</button>{error&&<p role="status">{error}</p>}</>:<><nav aria-label="Prepared stages">{reading.sections.map((s,i)=><button key={s.id} aria-current={section===i?'step':undefined} onClick={()=>{setSection(i);savePreference(key,String(i));}}>{s.title}</button>)}</nav>{reading.sections[section]&&<section><h3>{reading.sections[section].title}</h3><MediaSequence key={section} segments={reading.sections[section].segments} visuals={reading.sections[section].visuals} base={reading.base} record={record} identity={lesson+":"+section}/><MediaArtifacts animation={reading.sections[section].animation} clip={reading.sections[section].clip} base={reading.base} record={record}/></section>}</>}</details>;
}
