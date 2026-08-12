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

from config import (
    LLM_DEFAULT_MODEL,
    LLM_DEVICE,
    LLM_MAX_NEW_TOKENS,
    LLM_QUANTIZE,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_ATTEMPTS,
)
from schema import Presentation

from ai.validator import JSONParseError, strict_parse


class TransformersUnavailableError(RuntimeError):
    """Raised when torch/transformers are not installed."""


class JSONGenerator:
    """A thin, lazy wrapper around a transformers text-generation pipeline."""

    def __init__(self, model_name: str = LLM_DEFAULT_MODEL,
                 device: str = LLM_DEVICE,
                 quantize: bool = LLM_QUANTIZE,
                 temperature: float = LLM_TEMPERATURE,
                 max_new_tokens: int = LLM_MAX_NEW_TOKENS) -> None:
        self.model_name = model_name
        self.device = device
        self.quantize = quantize
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
        device = self.device
        if self.quantize:
            # 4-bit loading handles bigger models on a small GPU (e.g. Colab T4)
            kwargs["device_map"] = "auto"
            kwargs["model_kwargs"] = {"load_in_4bit": True}
        elif device in ("auto", "cuda", "gpu"):
            try:
                kwargs["device"] = 0 if torch.cuda.is_available() else -1
            except Exception:
                kwargs["device"] = -1
        elif device == "cpu":
            kwargs["device"] = -1
        else:
            kwargs["device"] = 0

        try:
            # Generation parameters (max_new_tokens / temperature) are passed
            # at call time as a single GenerationConfig; constructing the
            # pipeline with them triggers transformers deprecation warnings
            # about generation_config.
            return hf_pipeline(
                "text-generation",
                model=self.model_name,
                **kwargs,
            )
        except ImportError as exc:  # pragma: no cover - bitsandbytes missing
            raise TransformersUnavailableError(
                "Quantized loading needs `pip install bitsandbytes`. "
                "Or retry without --quantize."
            ) from exc

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
            f"   Output the deck exactly once; never repeat or echo it.\n"
            f"2. The JSON is an object with keys: \"title\", \"theme\" (optional), "
            f"\"slides\" (array).\n"
            f"3. Every slide has a \"type\" matching one of the allowed types and "
            f"the required fields for that type.\n"
            f"4. A comparison slide's \"comparisons\" is an array of objects; each "
            f"object uses the key \"heading\" (never \"name\" or \"title\") plus "
            f"\"current\" and \"future\" string values.\n"
            f"5. Keep each slide focused: at most 6 bullets/steps, at most 5 roadmap "
            f"phases, concise titles.\n"
            f"6. Write sharp, specific business language. Never invent fake statistics.\n\n"
            f"Example:\n"
            f'{{"title":"{topic}","theme":"corporate","slides":['
            f'{{"type":"title","title":"{topic}","subtitle":"Strategic overview","kicker":"Executive Briefing"}},'
            f'{{"type":"agenda","title":"Agenda","items":["Introduction","Impact assessment","Strategy development"]}},'
            f'{{"type":"bullets","title":"Why now","bullets":['
            f'{{"text":"Market forces are shifting decisively"}},'
            f'{{"text":"Technology has reached a tipping point"}}]}},'
            f'{{"type":"comparison","title":"Current vs Future","comparisons":['
            f'{{"heading":"Legacy Systems","current":"Slow to adapt, rigid, costly",'
            f'"future":"Flexible, scalable, cost-effective"}},'
            f'{{"heading":"Customer Experience","current":"Poor, fragmented, inconsistent",'
            f'"future":"Seamless and consistent"}}]}},'
            f'{{"type":"process","title":"How we will win","steps":["Discover","Design","Build","Launch"]}},'
            f'{{"type":"conclusion","title":"Next steps","takeaways":["Act now","Scale fast","Measure relentlessly"],'
            f'"cta":"Approve the plan"}}]}}\n\n'
            f"Now produce the JSON for the topic above:"
        )

    # -- generation ------------------------------------------------------
    def generate(self, topic: str, sections: Optional[list] = None,
                 tone: str = "professional") -> str:
        from transformers import GenerationConfig

        prompt = self.build_prompt(topic, sections, tone)
        # Pass a single `generation_config` rather than individual kwargs:
        # the text-generation pipeline injects its own generation_config into
        # `model.generate`, so extra kwargs both clash with it (deprecation
        # warning) and re-trigger the "max_new_tokens and max_length set"
        # warning.  max_length=None avoids that conflict; length is derived
        # from max_new_tokens at generate time.
        generation_config = GenerationConfig(
            max_new_tokens=self.max_new_tokens,
            max_length=None,
            temperature=self.temperature,
            do_sample=self.temperature > 0,
        )
        outputs = self.pipeline(prompt, generation_config=generation_config)
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
