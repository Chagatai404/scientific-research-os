import {pointLayout} from './graphLayout';
import type {GraphData} from './contracts';
const scope=self as unknown as {onmessage: ((event:MessageEvent<GraphData>)=>void)|null;postMessage(layout:ReturnType<typeof pointLayout>):void};
scope.onmessage=event=>scope.postMessage(pointLayout(event.data));
