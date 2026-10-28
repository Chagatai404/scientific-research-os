"""Explicit 10,000-file source scan/index/search benchmark in disposable storage."""
from pathlib import Path
import json
import os
import sys
import tempfile
import time
import statistics
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ros import api
from ros.store import Record

def main():
    folder=Path(tempfile.mkdtemp(prefix='source-benchmark-',dir=ROOT/'.desktop-fixtures'));source=folder/'source';source.mkdir()
    os.environ.update(ROS_NO_VAULT='1',ROS_HOME=str(folder/'home'))
    for i in range(10000):(source/f'n{i:05d}.md').write_text(f'# Synthetic note {i}\nbenchmarkneedle{i:05d}\n',encoding='utf-8')
    rec=Record(folder/'record')
    try:
        start=time.perf_counter();connection=api.call('source_register',rec,root=str(source),kind='folder')['id'];registration=time.perf_counter()-start
        pages=[];paths=[];start=time.perf_counter()
        for offset in range(0,10000,200):
            tick=time.perf_counter();rows=api.call('source_children',rec,source=connection,offset=offset,limit=200);pages.append(time.perf_counter()-tick);paths.extend(r['path'] for r in rows)
        listing=time.perf_counter()-start;assert len(paths)==10000
        start=time.perf_counter()
        for offset in range(0,len(paths),20):api.call('source_index_batch',rec,source=connection,paths=paths[offset:offset+20],generation='fixture')
        indexing=time.perf_counter()-start;searches=[]
        for _ in range(20):
            start=time.perf_counter();matches=api.call('source_search',rec,source=connection,q='benchmarkneedle09999');searches.append((time.perf_counter()-start)*1000)
        assert matches and 'n09999.md' in json.dumps(matches)
        report={'files':len(paths),'registration_ms':round(registration*1000,2),'listing_seconds':round(listing,3),'first_page_ms':round(pages[0]*1000,2),'last_page_ms':round(pages[-1]*1000,2),'index_seconds':round(indexing,3),'search_cold_ms':round(searches[0],2),'search_warm_p50_ms':round(statistics.median(searches[1:]),2),'search_warm_p95_ms':round(sorted(searches[1:])[18],2),'match_count':len(matches),'fixture':'10k small synthetic Markdown documents, unique lexical queries; excludes PDF OCR/model embedding.'}
        (ROOT/'docs/desktop-rebuild/source-performance.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    finally:rec.close();api.release()
if __name__=='__main__':main()
