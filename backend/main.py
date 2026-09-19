from pathlib import Path
from typing import List, Dict
import re, shutil
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader

BASE = Path(__file__).resolve().parent.parent
DOCS = BASE / 'data' / 'documents'
FRONTEND = BASE / 'frontend'
DOCS.mkdir(parents=True, exist_ok=True)
app = FastAPI(title='ROSE Project Intelligence System', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
INDEX: List[Dict] = []

def norm(s):
    for a,b in {'ي':'ی','ى':'ی','ك':'ک','ة':'ه','\u200c':' ','\u200f':' ','\ufeff':' '}.items(): s=(s or '').replace(a,b)
    return re.sub(r'\s+', ' ', s).strip().lower()

def index_pdf(path):
    reader=PdfReader(str(path)); added=0
    for n,page in enumerate(reader.pages,1):
        txt=page.extract_text() or ''
        if txt.strip():
            INDEX.append({'file':path.name,'page':n,'text':txt,'norm':norm(txt)}); added+=1
    return added,len(reader.pages)

def score(q,t):
    terms=[x for x in re.split(r'\s+',norm(q)) if len(x)>1]
    return sum(t.count(x) for x in terms)

@app.on_event('startup')
def startup():
    INDEX.clear()
    for p in DOCS.glob('*.pdf'):
        try: index_pdf(p)
        except Exception: pass

@app.get('/')
def home(): return FileResponse(FRONTEND/'index.html')

@app.get('/api/health')
def health(): return {'status':'online','system':'ROSE','documents':len({x['file'] for x in INDEX}),'indexed_pages':len(INDEX)}

@app.get('/api/documents')
def documents():
    d={}
    for x in INDEX: d[x['file']]=d.get(x['file'],0)+1
    return [{'file':k,'pages_indexed':v} for k,v in sorted(d.items())]

@app.post('/api/documents/upload')
async def upload(file: UploadFile=File(...)):
    if not file.filename.lower().endswith('.pdf'): return {'ok':False,'error':'فقط فایل PDF مجاز است.'}
    name=Path(file.filename).name; target=DOCS/name
    with target.open('wb') as out: shutil.copyfileobj(file.file,out)
    global INDEX; INDEX=[x for x in INDEX if x['file']!=name]
    pages,total=index_pdf(target)
    return {'ok':True,'file':name,'indexed_pages':pages,'total_pages':total}

@app.get('/api/search')
def search(q:str,limit:int=8):
    ranked=sorted(((score(q,x['norm']),x) for x in INDEX if score(q,x['norm'])),key=lambda z:z[0],reverse=True)
    out=[]
    for s,x in ranked[:max(1,min(limit,20))]: out.append({'score':s,'file':x['file'],'page':x['page'],'snippet':x['text'].replace('\n',' ')[:600]})
    return {'query':q,'results':out}

@app.post('/api/chat')
async def chat(payload:dict):
    q=str(payload.get('message','')).strip()
    if not q: return {'answer':'سؤال یا درخواست خود را وارد کنید.','sources':[]}
    ranked=sorted(((score(q,x['norm']),x) for x in INDEX if score(q,x['norm'])),key=lambda z:z[0],reverse=True)
    if not ranked: return {'answer':'در اسناد ایندکس‌شده، مستند قابل اتکایی برای این پرسش پیدا نشد. ROSE برای جلوگیری از پاسخ بدون منبع، نتیجه قطعی ارائه نمی‌کند.','sources':[]}
    top=ranked[:3]; sources=[{'file':x['file'],'page':x['page'],'score':s} for s,x in top]
    blocks=[f"منبع: {x['file']} | صفحه {x['page']}\n{x['text'].replace(chr(10),' ')[:900]}" for s,x in top]
    ans='بر اساس اسناد ایندکس‌شده، موارد زیر بیشترین تطابق را با درخواست شما دارند:\n\n'+'\n\n---\n\n'.join(blocks)+'\n\nاین نسخه MVP مبتنی بر جستجوی سندی است؛ مرحله بعد می‌تواند LLM/RAG، تحلیل قراردادی، مقایسه اسناد و Voice را اضافه کند.'
    return {'answer':ans,'sources':sources}

if __name__=='__main__':
    import uvicorn; uvicorn.run('main:app',host='0.0.0.0',port=8000,reload=True)
