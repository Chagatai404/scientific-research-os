"""Local-only bounded PDF page rendering; optional dependencies never enter the domain."""
import base64
import io
import json
import sys

def render(images):
    import pypdfium2
    result=[];notices=[]
    for image in images:
        if image['mime']!='application/pdf':result.append(image);continue
        document=pypdfium2.PdfDocument(base64.b64decode(image['data'],validate=True))
        try:
            total=len(document)
            notices.append({'revision':image['revision'],'total_pages':total,'included_pages':list(range(1,min(4,total)+1))})
            for index in range(min(4,total)):
                page=document[index]
                try:
                    width,height=page.get_size()
                    if not 0<width<=20000 or not 0<height<=20000:raise ValueError('PDF page dimensions exceed the safe rendering bound.')
                    bitmap=page.render(scale=min(1.3,2000/max(width,height)))
                    try:
                        with io.BytesIO() as stream:
                            bitmap.to_pil().save(stream,format='PNG')
                            result.append({'mime':'image/png','data':base64.b64encode(stream.getvalue()).decode(),'revision':image['revision'],'page':index+1})
                    finally:bitmap.close()
                finally:page.close()
        finally:document.close()
    return {'ok':True,'images':result,'page_scope':notices}

def main():
    try:result=render(json.load(sys.stdin)['images'])
    except Exception as exc:result={'ok':False,'error':'Local PDF rendering unavailable or failed: '+str(exc)[:200]}
    print(json.dumps(result));return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
