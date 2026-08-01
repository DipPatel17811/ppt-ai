"""Template base class and registry.

Every slide type is a **renderer** class.  The template decides *structure*
(kicker / title / layout / which primitives), never absolute coordinates --
those come from the layout engine via ``SlideBuilder``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Type

from builder import SlideBuilder


class BaseTemplate(ABC):
    """Base class for all slide templates."""

    kind: str = ""
    full_bleed: bool = False  # True = skip the standard footer

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.kind:
            TemplateRegistry.register(cls)

    @abstractmethod
    def render(self, b: SlideBuilder, content) -> None:
        """Render ``content`` onto the slide owned by ``b``."""


class TemplateRegistry:
    """Registry mapping slide-type names to their template classes."""

    _registry: Dict[str, Type[BaseTemplate]] = {}

    @classmethod
    def register(cls, template_cls: Type[BaseTemplate]) -> None:
        cls._registry[template_cls.kind] = template_cls

    @classmethod
    def get(cls, kind: str) -> Type[BaseTemplate]:
        if kind not in cls._registry:
            raise KeyError(
                f"No template registered for slide type {kind!r}. "
                f"Available: {sorted(cls._registry)}"
            )
        return cls._registry[kind]

    @classmethod
    def kinds(cls) -> list:
        return sorted(cls._registry)
