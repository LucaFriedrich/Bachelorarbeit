from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable
from llm.feedback.base import CompetencyLLM
from llm.feedback.types import FeedbackResult
from llm.shared.llm_factory import get_llm
from llm.shared.json_utils import clean_json_response
import json


class ClaudeLLM(CompetencyLLM):
    def __init__(self, prompt_template: PromptTemplate, model: str = None, model_type: str = "fast"):
        super().__init__()  # Initialisiert Logger
        self.prompt_template = prompt_template

        # Nutze das spezifische Model wenn gegeben, sonst Default
        if model:
            self.llm = get_llm(model=model, temperature=0.2)
        else:
            # Fallback auf Default-Modelle
            model_map = {
                "fast": "claude-3-haiku-20240307",
                "good": "claude-3-5-sonnet-20241022",
                "best": "claude-3-opus-20240229"
            }
            self.llm = get_llm(model=model_map.get(model_type, "claude-3-haiku-20240307"), temperature=0.2)

        self.logger.debug("Prompt-Template initialisiert:\n%s", self.prompt_template.template)

    def evaluate(self, abgabe: str, kompetenz: str) -> FeedbackResult:
        self.logger.debug("Aufruf von evaluate() mit:")
        self.logger.debug("Kompetenz:\n%s", kompetenz)
        self.logger.debug("Abgabe:\n%s", abgabe)

        try:
            prompt_str = self.prompt_template.format(abgabe=abgabe, kompetenz=kompetenz)
            self.logger.debug("Formatierter Claude-Prompt:\n%s", prompt_str)

            response = self.llm.invoke([HumanMessage(content=prompt_str)])
            self.logger.debug("LLM-Rohantwort:\n%s", response.content)
        except Exception as e:
            self.logger.error("Fehler beim LLM-Aufruf: %s", e)
            raise

        try:
            # WICHTIG: Bereinige die Antwort mit Claude-spezifischer Logik!
            cleaned_content = clean_json_response(response.content, provider="claude")
            parsed = json.loads(cleaned_content)
        except Exception as e:
            self.logger.error("Fehler beim Parsen der Antwort: %s", e)
            raise ValueError(f"Claude-Rückgabe konnte nicht geparsed werden: {e}\nAntwort war:\n{response.content}")

        if isinstance(parsed.get("kompetenz_erfüllt"), bool):
            parsed["kompetenz_erfüllt"] = (
                "funktional erfüllt" if parsed["kompetenz_erfüllt"] else "nicht sichtbar"
            )

        self.logger.info("Parsed Feedback erfolgreich erzeugt.")
        return FeedbackResult(**parsed)