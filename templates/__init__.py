"""Template package.  Importing this module registers every template."""

from templates.base import BaseTemplate, TemplateRegistry
from templates import (
    title,
    hero,
    agenda,
    bullets,
    comparison,
    timeline,
    process,
    roadmap,
    cycle,
    hierarchy,
    dashboard,
    swot,
    conclusion,
)

__all__ = ["BaseTemplate", "TemplateRegistry"]
