# llm/feedback/factory.py

from llm.feedback.openai_llm import OpenAILLM
from llm.feedback.claude_llm import ClaudeLLM
from llm.feedback.base import CompetencyLLM
from llm.feedback.prompts.builder import FeedbackPromptBuilder

def get_llm(llm_name: str = "openai", task_type: str = "python", model: str = None) -> CompetencyLLM:
    """
    Erstellt eine passende LLM-Instanz zur Kompetenzbewertung.

    Args:
        llm_name: Name des zu verwendenden LLMs (z. B. "openai", "claude")
        task_type: Aufgabentyp wie "python", "text", "java" etc.
        model: Spezifisches Model (z.B. "gpt-4o-mini", "claude-3-haiku-20240307")
               Wenn None, wird ein Default verwendet

    Returns:
        Instanz eines CompetencyLLM-Implementierers
    """
    prompt = FeedbackPromptBuilder.get_prompt(task_type)

    if llm_name == "openai":
        return OpenAILLM(prompt_template=prompt, model=model)

    if llm_name == "claude":
        return ClaudeLLM(prompt_template=prompt, model=model)

    raise ValueError(f"Unbekanntes LLM: {llm_name}")