from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable
from llm.feedback.base import CompetencyLLM
from llm.feedback.types import FeedbackResult
from llm.shared.llm_factory import get_llm
from llm.shared.json_utils import clean_json_response, parse_llm_json
import json


class OpenAILLM(CompetencyLLM):
    def __init__(self, prompt_template: PromptTemplate, model: str = None, model_type: str = "fast"):
        super().__init__()  # Initialisiert Logger aus Basisklasse

        self.prompt_template = prompt_template
        
        # Nutze das spezifische Model wenn gegeben, sonst Default
        if model:
            llm = get_llm(model=model, temperature=0.2)
        else:
            # Fallback auf Default-Modelle
            model_map = {
                "fast": "gpt-4o-mini",
                "good": "gpt-4o",
                "best": "o1-2024-12-17"
            }
            llm = get_llm(model=model_map.get(model_type, "gpt-4o-mini"), temperature=0.2)
        self.chain: Runnable = self.prompt_template | llm

        self.logger.debug("Prompt-Template initialisiert:\n%s", self.prompt_template.template)

    def evaluate(self, abgabe: str, kompetenz: str) -> FeedbackResult:
        # Logge die Inputs, die ans LLM gehen
        self.logger.debug("Aufruf von evaluate() mit:")
        self.logger.debug("Kompetenz:\n%s", kompetenz)
        self.logger.debug("Abgabe:\n%s", abgabe)

        try:
            response = self.chain.invoke({
                "kompetenz": kompetenz,
                "abgabe": abgabe
            })
            self.logger.debug("LLM-Rohantwort:\n%s", response.content)
        except Exception as e:
            self.logger.error("Fehler beim Aufruf der LLM-Chain: %s", e)
            raise

        try:
            # WICHTIG: Bereinige die Antwort vor dem Parsen!
            cleaned_content = clean_json_response(response.content)
            self.logger.debug(" JSON Response (bereinigt):\n%s", cleaned_content)
            parsed = json.loads(cleaned_content)
            self.logger.debug(" Parsed JSON: %s", parsed)
        except Exception as e:
            self.logger.error("Fehler beim Parsen der Antwort: %s", e)
            self.logger.error("Raw response war: %s", response.content)
            raise ValueError(f"Fehler beim Parsen der LLM-Antwort: {e}\nAntwort war:\n{response.content}")

        # ️ Soft-Fallback
        if isinstance(parsed.get("kompetenz_erfüllt"), bool):
            parsed["kompetenz_erfüllt"] = (
                "funktional erfüllt" if parsed["kompetenz_erfüllt"] else "nicht sichtbar"
            )

        self.logger.info("Parsed Feedback erfolgreich erzeugt.")
        return FeedbackResult(**parsed)