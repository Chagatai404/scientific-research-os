import {useState} from 'react';
import {call} from './api';
import {Result} from './Workbench';
export function VaultActions({record}:{record:string}){
 const [open,setOpen]=useState(false);
 const [result,setResult]=useState<unknown>(),[target,setTarget]=useState(''),[action,setAction]=useState('reviewed'),[status,setStatus]=useState('');
 async function run(name:string,args:Record<string,unknown>){try{setResult(await call(name,args,record,true));setStatus('Operation completed. Inspect the saved result.');}catch(e){setStatus((e as Error).message);}}
 return <details onToggle={event=>setOpen(event.currentTarget.open)}><summary>Vault Sync &amp; Conflict Resolution</summary>{open&&<><p>Preview before writing. Generated regions preserve My Notes; conflict resolution keeps the user's prior text.</p><div className="actions"><button onClick={()=>run('vault_sync',{dry_run:true})}>Preview Vault Sync</button><button onClick={()=>run('vault_sync',{})}>Synchronize This Record</button></div><label>Conflicting Note ID or Relative Path<input value={target} onChange={e=>setTarget(e.target.value)}/></label><label>Resolution<select value={action} onChange={e=>setAction(e.target.value)}><option value="reviewed">Mark Reviewed</option><option value="restore">Restore Deleted Generated Note</option><option value="update">Update Generated Region and Preserve My Notes</option></select></label><button disabled={!target.trim()} onClick={()=>run('vault_resolve',{target,action})}>Apply Note Resolution</button>{status&&<p role="status">{status}</p>}{result!==undefined&&<Result value={result} record={record}/>}</>}</details>;
}
