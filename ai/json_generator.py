"""Strict-JSON LLM generation via HuggingFace ``transformers``.

Only *this* module talks to a language model.  It is fully optional: when
``torch``/``transformers`` are not installed, callers should fall back to
the deterministic planner (see ``planner.py``).

Supported families: Qwen, Llama, Gemma (any instruct model works in
principle).  The generator enforces JSON output by (a) instructing the model
to emit nothing but JSON and (b) validating the result against the schema
with retries.
"""

from __future__ import annotations

import json
from typing import Optional

from config import LLM_DEFAULT_MODEL, LLM_MAX_NEW_TOKENS, LLM_TEMPERATURE, LLM_TIMEOUT_ATTEMPTS
from schema import Presentation

from ai.validator import JSONParseError, strict_parse


class TransformersUnavailableError(RuntimeError):
    """Raised when torch/transformers are not installed."""


class JSONGenerator:
    """A thin, lazy wrapper around a transformers text-generation pipeline."""

    def __init__(self, model_name: str = LLM_DEFAULT_MODEL,
                 device: str = "auto",
                 temperature: float = LLM_TEMPERATURE,
                 max_new_tokens: int = LLM_MAX_NEW_TOKENS) -> None:
        self.model_name = model_name
        self.device = device
        self.temperature = temperature
        self.max_new_tokens = max_new_tokens
        self._pipeline = None

    # -- lazy model load -------------------------------------------------
    @property
    def pipeline(self):
        if self._pipeline is None:
            self._pipeline = self._build_pipeline()
        return self._pipeline

    def _build_pipeline(self):
        try:
            import torch  # noqa: F401
            from transformers import pipeline as hf_pipeline
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise TransformersUnavailableError(
                "torch / transformers are not installed. Install them with "
                "`pip install torch transformers` or use mode='deterministic'."
            ) from exc
        kwargs = {}
        if self.device == "cpu":
            kwargs["device"] = -1
        return hf_pipeline(
            "text-generation",
            model=self.model_name,
            max_new_tokens=self.max_new_tokens,
            temperature=self.temperature,
            do_sample=self.temperature > 0,
            **kwargs,
        )

    # -- prompt ----------------------------------------------------------
    @staticmethod
    def build_prompt(topic: str, sections: Optional[list] = None,
                     tone: str = "professional") -> str:
        kinds = [
            "title", "hero", "agenda", "bullets", "comparison", "timeline",
            "process", "roadmap", "cycle", "hierarchy", "dashboard", "swot",
            "conclusion",
        ]
        asked = ", ".join(sections) if sections else "a balanced executive deck"
        return (
            f"You are a world-class strategy consultant writing a business presentation.\n"
            f"Topic: {topic}\n"
            f"Tone: {tone}. Audience: C-level executives.\n\n"
            f"Produce {asked}. Use only these slide types: {', '.join(kinds)}.\n\n"
            f"STRICT OUTPUT RULES:\n"
            f"1. Output ONLY valid JSON. No markdown, no code fences, no commentary.\n"
            f"2. The JSON is an object with keys: \"title\", \"theme\" (optional), "
            f"\"slides\" (array).\n"
            f"3. Every slide has a \"type\" matching one of the allowed types and "
            f"the required fields for that type.\n"
            f"4. Keep each slide focused: at most 6 bullets/steps, at most 5 roadmap "
            f"phases, concise titles.\n"
            f"5. Write sharp, specific business language. Never invent fake statistics.\n\n"
            f"Example:\n"
            f'{{"title":"{topic}","theme":"corporate","slides":['
            f'{{"type":"title","title":"{topic}","subtitle":"Strategic overview","kicker":"Executive Briefing"}},'
            f'{{"type":"bullets","title":"Why now","bullets":['
            f'{{"text":"Market forces are shifting decisively"}},'
            f'{{"text":"Technology has reached a tipping point"}}]}},'
            f'{{"type":"process","title":"How we will win","steps":["Discover","Design","Build","Launch"]}},'
            f'{{"type":"conclusion","title":"Next steps","takeaways":["Act now","Scale fast","Measure relentlessly"],'
            f'"cta":"Approve the plan"}}]}}\n\n'
            f"Now produce the JSON for the topic above:"
        )

    # -- generation ------------------------------------------------------
    def generate(self, topic: str, sections: Optional[list] = None,
                 tone: str = "professional") -> str:
        prompt = self.build_prompt(topic, sections, tone)
        outputs = self.pipeline(prompt, max_new_tokens=self.max_new_tokens)
        text = outputs[0]["generated_text"]
        # strip the prompt echo if the model repeats it
        if text.startswith(prompt):
            text = text[len(prompt):]
        return text

    def generate_ast(self, topic: str, sections: Optional[list] = None,
                     tone: str = "professional") -> Presentation:
        """Generate and strictly validate a Presentation AST with retries."""
        last_error: Optional[JSONParseError] = None
        for attempt in range(LLM_TIMEOUT_ATTEMPTS):
            raw = self.generate(topic, sections, tone)
            try:
                return strict_parse(raw)
            except JSONParseError as exc:
                last_error = exc
        assert last_error is not None
        raise last_error
