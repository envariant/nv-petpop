from backend.core.parser import parse


class RuleParser:
    """Stage A in mock mode: the rule-based parser over vocab.json (no LLM)."""
    name = "rules"

    def available(self) -> bool:
        return True

    def parse(self, text, species, current, tapped):
        return parse(text, species, current, tapped)
