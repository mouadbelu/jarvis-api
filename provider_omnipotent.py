import os
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

class OmnipotentProvider:
    def __init__(self):
        self.oai = AsyncOpenAI(api_key=os.getenv("JARVIS_OPENAI_KEY"))
        self.claude = AsyncAnthropic(api_key=os.getenv("JARVIS_CLAUDE_KEY")) if os.getenv("JARVIS_CLAUDE_KEY") else None
        self.gemini_key = os.getenv("JARVIS_GEMINI_KEY")

    async def complete(self, messages):
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        is_code = "```" in msgs[-1]["content"] or "code" in msgs[-1]["content"].lower()
        try:
            if is_code and self.claude:
                r = await self.claude.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=4096, messages=msgs)
                return r.content[0].text
        except Exception as e:
            print(f"Claude fallback: {e}")
        r = await self.oai.chat.completions.create(model="gpt-4o-mini", messages=msgs)
        return r.choices[0].message.content
