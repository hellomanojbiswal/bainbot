"""Bounded agent loop: one prompt, optional search calls, final written output.
No arbitrary code, URLs, browser actions or external writes can be executed.
"""
import json
from fastapi import HTTPException
from backend.provider import complete

SEARCH_TOOL={'type':'function','function':{'name':'search_web','description':'Find public web sources relevant to the user request. Use only when fresh or external facts are needed.','parameters':{'type':'object','properties':{'query':{'type':'string','maxLength':400}},'required':['query'],'additionalProperties':False}}}

async def run_workflow(messages,model,allow_search,before_model,search,progress):
    history=list(messages);used=0;sources=[]
    for step in range(3):
        before_model()
        progress('Preparing the response' if step==2 else 'Planning and writing' if not used else 'Reviewing research and writing')
        reply=await complete(history,model,tools=[SEARCH_TOOL] if allow_search else None,tool_choice='none' if step==2 or used>=2 else 'auto')
        calls=reply.get('tool_calls') or []
        if calls:
            if not allow_search or step==2 or used+len(calls)>2:raise HTTPException(502,'The model exceeded this task’s research limit. Try a narrower request.')
            checked=[]
            for call in calls:
                try:
                    function=call['function'];args=json.loads(function['arguments'])
                    query=args['query'];call_id=call['id']
                    if function['name']!='search_web' or not isinstance(query,str) or not query.strip() or len(query)>400 or not isinstance(call_id,str) or not call_id:raise ValueError()
                    checked.append((call_id,query.strip()))
                except (KeyError,ValueError,TypeError):raise HTTPException(502,'The model requested an invalid tool. Try another model or rephrase the task.')
            history.append({'role':'assistant','content':reply.get('content') or None,'tool_calls':calls})
            for call_id,query in checked:
                progress('Researching: '+query)
                result=await search(query);used+=1
                sources.extend(line for line in result.splitlines() if line.startswith(('https://','http://')))
                history.append({'role':'tool','tool_call_id':call_id,'content':result})
            continue
        content=reply.get('content')
        if not isinstance(content,str) or not content.strip():raise HTTPException(502,'The model returned no final text. Try again or choose another model.')
        if sources:content+='\n\n## Sources consulted\n'+'\n'.join(dict.fromkeys(sources))
        return content
    raise HTTPException(502,'The task did not finish within its step limit.')
