"""Conversation style guard: do not greet the user on every assistant turn."""
import re

_GREETING = re.compile(
    r"^\s*(?:(?:buongiorno|buonasera|buon pomeriggio|ciao|salve|ehi|hey)"
    r"\s*[,!:–\-]*\s*(?:moed|mouad)?\s*[,!:–\-\.]*\s*)+",
    re.IGNORECASE,
)
_NAME_ONLY = re.compile(r"^\s*(?:moed|mouad)\s*[,!:–\-]+\s*", re.IGNORECASE)


def clean_repeated_greeting(reply: str, previous_turns: int) -> str:
    """Remove only boilerplate leading greetings after a conversation began.

    Preserve the user's requested message text itself and all first greetings.
    """
    if not isinstance(reply, str) or previous_turns <= 0:
        return reply
    value = reply
    for _ in range(2):
        new = _GREETING.sub('', value, count=1)
        if new == value:
            new = _NAME_ONLY.sub('', value, count=1)
        if new == value:
            break
        value = new.lstrip()
    if not value:
        return reply
    return value[0].upper() + value[1:] if value[0].islower() else value
