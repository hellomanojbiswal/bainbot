"""OpenRouter and other OpenAI-compatible Chat Completions providers."""
import os
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException

async def complete(messages,model='',tools=None,tool_choice='auto'):
    key=os.getenv('LLM_API_KEY','');base=os.getenv('LLM_BASE_URL','').rstrip('/');model=model or os.getenv('LLM_MODEL','')
    if not key or not base or not model:raise HTTPException(503,'Set LLM_API_KEY, LLM_BASE_URL and LLM_MODEL on the server.')
    parsed=urlparse(base)
    if parsed.scheme!='https' and not(parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost')):
        raise HTTPException(503,'LLM_BASE_URL must use HTTPS (localhost HTTP is allowed for tests).')
    payload={'model':model,'messages':messages}
    if tools:payload.update(tools=tools,tool_choice=tool_choice)
    cap=os.getenv('LLM_OUTPUT_LIMIT')
    if cap:payload[os.getenv('LLM_TOKEN_LIMIT_FIELD','max_tokens')]=int(cap)
    headers={'Authorization':'Bearer '+key}
    if parsed.hostname=='openrouter.ai':
        headers['X-OpenRouter-Title']='Bainbot'
        if os.getenv('PUBLIC_ORIGIN'):headers['HTTP-Referer']=os.environ['PUBLIC_ORIGIN']
    try:
        async with httpx.AsyncClient(timeout=float(os.getenv('LLM_TIMEOUT_SECONDS','45'))) as client:
            r=await client.post(base+'/chat/completions',headers=headers,json=payload)
            r.raise_for_status();message=r.json()['choices'][0]['message']
            if not isinstance(message,dict):raise ValueError('Invalid message')
            return message
    except httpx.TimeoutException:raise HTTPException(504,'The AI provider timed out. Try again.')
    except httpx.HTTPStatusError as e:
        code=e.response.status_code
        detail='Check your API key and provider permissions.' if code in (401,403) else 'Check your provider credits and rate limits.' if code in (402,429) else 'Check your model name, base URL and provider status.'
        raise HTTPException(502,'AI provider rejected the request. '+detail)
    except Exception:raise HTTPException(502,'The provider returned an invalid response. Use an OpenAI-compatible Chat Completions endpoint.')

async def generate(messages,model=''):
    message=await complete(messages,model)
    content=message.get('content')
    if not isinstance(content,str) or not content.strip():raise HTTPException(502,'The provider returned no text. Try another model.')
    return content
