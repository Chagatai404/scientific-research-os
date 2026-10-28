import {useState} from 'react';
import {call, href, preference} from './api';
import {DEFAULT_MODEL, normalizeModel} from './modelPreferences';
export function AgentAction({record,text,mode='learn',label='Ask Connected Tutor'}: {record:string;text:string;mode?:string;label?:string}) {
  const [status,setStatus]=useState(''),[busy,setBusy]=useState(false),[conversation,setConversation]=useState('');
  async function start(){setBusy(true);try{const model=normalizeModel(preference('model',DEFAULT_MODEL)); const result=await call<{conversation:string}>('workspace_chat_send',{text,model,mode,key:crypto.randomUUID(),...(model.startsWith('codex:')?{effort:preference('effort','medium')}:{})},record,true);setConversation(result.conversation);setStatus('Run queued. Results remain linked to this session and its original attempts.');}catch(e){setStatus((e as Error).message);}finally{setBusy(false);}}
  return <div className="agent-action"><button type="button" disabled={busy} onClick={start}>{busy?'Starting…':label}</button>{status&&<p role="status">{status}</p>}{conversation&&<a href={href('chat',conversation,record)}>Inspect Tutor Run</a>}</div>;
}
