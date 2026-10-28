import type {GraphData} from './contracts';
import type {pointLayout} from './graphLayout';
export type GraphLayout = ReturnType<typeof pointLayout>;
export interface LayoutWorker {
  onmessage: ((event: MessageEvent<GraphLayout>) => void)|null;
  onerror: ((event: ErrorEvent) => void)|null;
  onmessageerror: ((event: MessageEvent) => void)|null;
  postMessage(graph: GraphData): void;
  terminate(): void;
}
export function startLayout(worker: LayoutWorker, graph: GraphData, deliver: (layout: GraphLayout)=>void, fail: ()=>void) {
  let active=true;
  const stop=()=>{if(!active)return;active=false;worker.onmessage=null;worker.onerror=null;worker.onmessageerror=null;worker.terminate();};
  worker.onmessage=event=>{if(active){deliver(event.data);stop();}};
  worker.onerror=worker.onmessageerror=()=>{if(active){stop();fail();}};
  try{worker.postMessage(graph);}catch{stop();fail();}
  return stop;
}
