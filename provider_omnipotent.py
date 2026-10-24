"""LLM providers with environment-only API keys (never expose to browser)."""
import os
import httpx

SYSTEM_PROMPT = (
    'Sei Jarvis, l’assistente personale di Mouad. Rispondi in italiano, con precisione, ' 
    'senza inventare accesso a email o app. Non affermare di aver inviato messaggi ' 
    'o compiuto azioni se non le hai realmente completate. Quando un’azione ha ' 
    'conseguenze esterne, ricorda che richiede conferma esplicita.'
)


async def omnipotent_ask(prompt: str, sys: str | None = None) -> str | None:
    system = (sys or SYSTEM_PROMPT)[:10000]
    timeout = httpx.Timeout(35.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if os.getenv('JARVIS_OPENAI_KEY'):
            try:
                response = await client.post('https://api.openai.com/v1/chat/completions',
                    headers={'Authorization': 'Bearer ' + os.environ['JARVIS_OPENAI_KEY']},
                    json={'model': os.getenv('JARVIS_OPENAI_MODEL', 'gpt-4o-mini'),
                          'messages': [{'role':'system','content':system},{'role':'user','content':prompt}]})
                response.raise_for_status()
                answer = response.json()['choices'][0]['message']['content']
                if answer:
                    return answer
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                print('OpenAI request failed:', type(exc).__name__)
        if os.getenv('JARVIS_GEMINI_KEY'):
            try:
                response = await client.post('https://generativelanguage.googleapis.com/v1beta/models/'
                    + os.getenv('JARVIS_GEMINI_MODEL', 'gemini-2.5-flash') + ':generateContent',
                    headers={'x-goog-api-key': os.environ['JARVIS_GEMINI_KEY']},
                    json={'systemInstruction': {'parts':[{'text':system}]},
                          'contents': [{'parts':[{'text':prompt}]}]})
                response.raise_for_status()
                return response.json()['candidates'][0]['content']['parts'][0]['text']
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                print('Gemini request failed:', type(exc).__name__)
        if os.getenv('JARVIS_CLAUDE_KEY'):
            try:
                response = await client.post('https://api.anthropic.com/v1/messages',
                    headers={'x-api-key': os.environ['JARVIS_CLAUDE_KEY'], 'anthropic-version':'2023-06-01'},
                    json={'model': os.getenv('JARVIS_CLAUDE_MODEL', 'claude-sonnet-4-5'),
                          'max_tokens': 1000, 'system': system,
                          'messages':[{'role':'user','content':prompt}]})
                response.raise_for_status()
                return response.json()['content'][0]['text']
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                print('Claude request failed:', type(exc).__name__)
    return None

ask_omnipotent = omnipotent_ask
