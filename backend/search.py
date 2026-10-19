"""Read-only web search adapters. Credentials never leave the backend."""
import os
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException

def search_provider():
    return os.getenv('SEARCH_PROVIDER','tinyfish' if os.getenv('TINYFISH_API_KEY') else 'tavily').lower()
def search_configured():
    name=search_provider()
    return name in ('tinyfish','tavily') and bool(os.getenv('TINYFISH_API_KEY' if name=='tinyfish' else 'TAVILY_API_KEY'))

async def search_web(query):
    provider=search_provider()
    if not search_configured():raise HTTPException(503,'Configure SEARCH_PROVIDER and its TINYFISH_API_KEY or TAVILY_API_KEY on the server.')
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            if provider=='tinyfish':
                r=await client.get('https://api.search.tinyfish.ai',headers={'X-API-Key':os.environ['TINYFISH_API_KEY']},params={'query':query})
            else:
                r=await client.post('https://api.tavily.com/search',headers={'Authorization':'Bearer '+os.environ['TAVILY_API_KEY']},json={'query':query,'search_depth':'basic','max_results':5,'include_answer':True,'include_raw_content':False})
            r.raise_for_status();data=r.json()
        if not isinstance(data,dict) or not isinstance(data.get('results'),list):raise ValueError('Invalid search response')
        sections=['## Web research','Search results from '+provider.title()+'. This is research, not an action performed in another app.']
        if isinstance(data.get('answer'),str) and data['answer'].strip():sections.append(data['answer'][:6000])
        for item in data['results'][:5]:
            url=item.get('url','')
            if not isinstance(url,str) or urlparse(url).scheme not in ('https','http'):continue
            sections.append('### '+str(item.get('title','Source'))[:250]+'\n'+url+'\n'+str(item.get('snippet') or item.get('content',''))[:2000])
        if len(sections)==2:sections.append('No matching results were returned. Try a more specific search.')
        return '\n\n'.join(sections)
    except httpx.TimeoutException:raise HTTPException(504,'Web research timed out. Please try again.')
    except httpx.HTTPStatusError as e:
        hint='Check the search API key and permissions.' if e.response.status_code in (401,403) else 'Check search credits, request limits and provider availability.'
        raise HTTPException(502,'Web research was unavailable. '+hint)
    except Exception:raise HTTPException(502,'The search provider returned an unexpected response. Please try again.')
