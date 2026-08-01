"""The strongly-typed Presentation AST.

The whole pipeline is built around this contract:

    LLM  ->  Presentation AST (JSON)  ->  Validation  ->  Template  ->  Layout
          ->  Renderer  ->  PowerPoint Compiler  ->  editable .pptx

The AST is expressed with Pydantic models so that:

* AI output can be validated, coerced and repaired deterministically;
* no dictionary access ever happens downstream (everything is typed);
* the JSON schema can be exported for prompt engineering.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from config import (
    MAX_BULLETS_PER_LIST,
    MAX_CHART_CATEGORIES,
    MAX_CHART_SERIES,
    MAX_COMPARISON_POINTS,
    MAX_DASHBOARD_METRICS,
    MAX_HIERARCHY_NODES,
    MAX_PHASES,
    MAX_PIE_SLICES,
    MAX_STEPS,
    MAX_SWOT_ITEMS,
    MAX_TIMELINE_ITEMS,
)
from utils import colors


class AspectRatio(str, Enum):
    SIXTEEN_NINE = "16:9"
    SIXTEEN_TEN = "16:10"
    FOUR_THREE = "4:3"


class ThemeMode(str, Enum):
    LIGHT = "light"
    DARK = "dark"


class TextAlign(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class VerticalAlign(str, Enum):
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class FitMode(str, Enum):
    CONTAIN = "contain"
    COVER = "cover"


class ChartKind(str, Enum):
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    AREA = "area"
    SCATTER = "scatter"


class PhaseStatus(str, Enum):
    DONE = "done"
    CURRENT = "current"
    NEXT = "next"
    PLANNED = "planned"


class SemanticAnimation(str, Enum):
    NONE = "none"
    EXECUTIVE_REVEAL = "executive_reveal"
    PROCESS_BUILD = "process_build"
    DASHBOARD_FOCUS = "dashboard_focus"
    COMPARE = "compare"
    TIMELINE = "timeline"


class TransitionKind(str, Enum):
    NONE = "none"
    FADE = "fade"
    PUSH = "push"
    WIPE = "wipe"
    MORPH = "morph"


class TransitionDirection(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


# ---------------------------------------------------------------------------
# Small value objects
# ---------------------------------------------------------------------------


class ColorString(str):
    """Normalised ``#RRGGBB`` colour used by the validator for `color` fields."""


class TextStyle(BaseModel):
    """Optional styling overrides applied on top of the theme defaults."""

    model_config = ConfigDict(extra="forbid")

    color: Optional[str] = None
    size: Optional[float] = Field(default=None, gt=0)
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    letter_spacing: Optional[float] = Field(default=None, ge=0)
    line_spacing: Optional[float] = Field(default=None, gt=0)
    align: Optional[TextAlign] = None

    @field_validator("color")
    @classmethod
    def _check_color(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else colors.normalize(v)


class BulletItem(BaseModel):
    """A single bullet with optional emphasis and icon."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    level: int = Field(default=0, ge=0, le=2)
    icon: Optional[str] = None
    highlight: bool = False
    style: Optional[TextStyle] = None


class ImageSpec(BaseModel):
    """An image sourced from a local path, URL or future AI renderer."""

    model_config = ConfigDict(extra="forbid")

    source: str
    fit: FitMode = FitMode.COVER
    align_x: float = Field(default=0.5, ge=0, le=1)
    align_y: float = Field(default=0.5, ge=0, le=1)
    radius: Optional[float] = Field(default=None, ge=0)
    alt_text: Optional[str] = None


class ChartSeries(BaseModel):
    """One data series of a chart."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    values: List[float]
    color: Optional[str] = None

    @field_validator("color")
    @classmethod
    def _check_color(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else colors.normalize(v)


class ChartSpec(BaseModel):
    """A chart described purely in terms of structured data.

    The compiler turns this into a *native, editable* PowerPoint chart.  No
    manual drawing ever happens.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ChartKind = ChartKind.BAR
    title: Optional[str] = None
    subtitle: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    series: List[ChartSeries] = Field(default_factory=list)
    scatter_points: Optional[List[Tuple[float, float]]] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    stacked: bool = False
    horizontal: bool = False
    show_legend: bool = True
    show_value_labels: bool = False
    show_gridlines: bool = True

    @field_validator("categories")
    @classmethod
    def _strip_empty(cls, v: List[str]) -> List[str]:
        return [c for c in v if c]

    @model_validator(mode="after")
    def _check_consistency(self) -> "ChartSpec":
        if self.kind == ChartKind.SCATTER:
            if self.scatter_points is None:
                raise ValueError("Scatter charts require scatter_points")
        else:
            if not self.categories:
                raise ValueError(f"{self.kind.value} charts require categories")
            if not self.series:
                raise ValueError(f"{self.kind.value} charts require at least one series")
            if len(self.categories) > MAX_CHART_CATEGORIES:
                raise ValueError(f"Too many categories ({len(self.categories)} > {MAX_CHART_CATEGORIES})")
            if len(self.series) > MAX_CHART_SERIES:
                raise ValueError(f"Too many series ({len(self.series)} > {MAX_CHART_SERIES})")
            for s in self.series:
                if len(s.values) != len(self.categories):
                    raise ValueError(
                        f"Series {s.name!r} has {len(s.values)} values "
                        f"but {len(self.categories)} categories"
                    )
        if self.kind == ChartKind.PIE:
            if self.categories and len(self.categories) > MAX_PIE_SLICES:
                raise ValueError(f"Too many pie slices ({len(self.categories)} > {MAX_PIE_SLICES})")
        return self


class TimelineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Optional[str] = None
    title: str = Field(min_length=1)
    detail: Optional[str] = None


class ComparisonColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = Field(min_length=1)
    subheading: Optional[str] = None
    points: List[str] = Field(default_factory=list)
    icon: Optional[str] = None

    @model_validator(mode="after")
    def _limit_points(self) -> "ComparisonColumn":
        if len(self.points) > MAX_COMPARISON_POINTS:
            raise ValueError(f"Too many comparison points ({len(self.points)})")
        return self


class RoadmapPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    period: Optional[str] = None
    items: List[str] = Field(default_factory=list)
    status: PhaseStatus = PhaseStatus.PLANNED

    @model_validator(mode="after")
    def _limit_items(self) -> "RoadmapPhase":
        if len(self.items) > 4:
            raise ValueError(f"Roadmap phase {self.name!r} has too many items ({len(self.items)})")
        return self


class MetricCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    delta: Optional[str] = None
    delta_good: bool = True
    icon: Optional[str] = None
    note: Optional[str] = None


class HierarchyNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    role: Optional[str] = None
    children: List["HierarchyNode"] = Field(default_factory=list)


class SwoQuadrant(BaseModel):
    """One quadrant of a SWOT-style 2x2 grid."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    items: List[str] = Field(default_factory=list)


class TransitionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TransitionKind = TransitionKind.FADE
    duration_ms: int = Field(default=600, ge=0, le=5000)
    direction: Optional[TransitionDirection] = None

    @model_validator(mode="after")
    def _require_direction(self) -> "TransitionSpec":
        if self.kind in (TransitionKind.PUSH, TransitionKind.WIPE) and self.direction is None:
            self.direction = TransitionDirection.LEFT
        return self


class ThemeSpec(BaseModel):
    """The full set of colours, fonts and spacing for a deck.

    If no inline spec is provided the compiler falls back to a named built-in
    theme (see ``theme.py`` / ``assets/themes``).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = "custom"
    mode: ThemeMode = ThemeMode.LIGHT
    background: str = "#ffffff"
    foreground: str = "#1a2233"
    muted: str = "#5b6b7c"
    primary: str = "#0f4c81"
    secondary: str = "#2e9e8f"
    accent: str = "#e9a13b"
    success: str = "#2e9e5b"
    warning: str = "#d97b29"
    danger: str = "#c0392b"
    heading_font: str = "Segoe UI"
    body_font: str = "Segoe UI"
    mono_font: str = "Consolas"
    base_spacing: float = 8.0
    corner_radius: float = 8.0
    footer_text: str = "Confidential"
    chart_palette: List[str] = Field(
        default_factory=lambda: ["#0f4c81", "#2e9e8f", "#e9a13b", "#c0392b", "#6b5b95", "#3a6ea5", "#5b6b7c"]
    )

    @field_validator(
        "background", "foreground", "muted", "primary", "secondary",
        "accent", "success", "warning", "danger", "chart_palette",
    )
    @classmethod
    def _normalize_colors(cls, v):
        if isinstance(v, list):
            return [colors.normalize(c) for c in v]
        return colors.normalize(v)


# ---------------------------------------------------------------------------
# Slide models (one per template)
# ---------------------------------------------------------------------------


class SlideBase(BaseModel):
    """Common fields shared by every slide."""

    model_config = ConfigDict(extra="forbid")

    type: str
    notes: Optional[str] = None
    animation: SemanticAnimation = SemanticAnimation.NONE
    transition: Optional[TransitionSpec] = None
    kicker: Optional[str] = None


class TitleSlide(SlideBase):
    type: Literal["title"] = "title"
    title: str = Field(min_length=1)
    subtitle: Optional[str] = None
    presenter: Optional[str] = None
    date: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class HeroSlide(SlideBase):
    type: Literal["hero"] = "hero"
    title: str = Field(min_length=1)
    subtitle: Optional[str] = None
    image: Optional[ImageSpec] = None
    tags: List[str] = Field(default_factory=list)
    cta: Optional[str] = None


class AgendaSlide(SlideBase):
    type: Literal["agenda"] = "agenda"
    title: str = Field(min_length=1)
    items: List[str] = Field(default_factory=list, min_length=1)


class BulletsSlide(SlideBase):
    type: Literal["bullets"] = "bullets"
    title: str = Field(min_length=1)
    intro: Optional[str] = None
    bullets: List[BulletItem] = Field(default_factory=list, min_length=1)
    image: Optional[ImageSpec] = None
    chart: Optional[ChartSpec] = None

    @model_validator(mode="after")
    def _limit(self) -> "BulletsSlide":
        if len(self.bullets) > MAX_BULLETS_PER_LIST:
            raise ValueError(f"Too many bullets ({len(self.bullets)} > {MAX_BULLETS_PER_LIST})")
        return self


class ComparisonSlide(SlideBase):
    type: Literal["comparison"] = "comparison"
    title: str = Field(min_length=1)
    context: Optional[str] = None
    left: ComparisonColumn = Field(default_factory=ComparisonColumn)
    right: ComparisonColumn = Field(default_factory=ComparisonColumn)
    bottom_line: Optional[str] = None


class TimelineSlide(SlideBase):
    type: Literal["timeline"] = "timeline"
    title: str = Field(min_length=1)
    items: List[TimelineItem] = Field(default_factory=list, min_length=1)

    @model_validator(mode="after")
    def _limit(self) -> "TimelineSlide":
        if len(self.items) > MAX_TIMELINE_ITEMS:
            raise ValueError(f"Too many timeline items ({len(self.items)})")
        return self


class ProcessSlide(SlideBase):
    type: Literal["process"] = "process"
    title: str = Field(min_length=1)
    subtitle: Optional[str] = None
    steps: List[str] = Field(default_factory=list, min_length=2)

    @model_validator(mode="after")
    def _limit(self) -> "ProcessSlide":
        if len(self.steps) > MAX_STEPS:
            raise ValueError(f"Too many process steps ({len(self.steps)})")
        return self


class RoadmapSlide(SlideBase):
    type: Literal["roadmap"] = "roadmap"
    title: str = Field(min_length=1)
    intro: Optional[str] = None
    phases: List[RoadmapPhase] = Field(default_factory=list, min_length=1)

    @model_validator(mode="after")
    def _limit(self) -> "RoadmapSlide":
        if len(self.phases) > MAX_PHASES:
            raise ValueError(f"Too many roadmap phases ({len(self.phases)})")
        return self


class CycleSlide(SlideBase):
    type: Literal["cycle"] = "cycle"
    title: str = Field(min_length=1)
    stages: List[str] = Field(default_factory=list, min_length=3)
    center_label: Optional[str] = None

    @model_validator(mode="after")
    def _limit(self) -> "CycleSlide":
        if len(self.stages) > MAX_STEPS:
            raise ValueError(f"Too many cycle stages ({len(self.stages)})")
        return self


class HierarchySlide(SlideBase):
    type: Literal["hierarchy"] = "hierarchy"
    title: str = Field(min_length=1)
    root: HierarchyNode = Field(default_factory=HierarchyNode)

    @model_validator(mode="after")
    def _limit(self) -> "HierarchySlide":
        count = 0

        def walk(node: HierarchyNode) -> None:
            nonlocal count
            count += 1
            for child in node.children:
                walk(child)

        walk(self.root)
        if count > MAX_HIERARCHY_NODES:
            raise ValueError(f"Hierarchy too large ({count} nodes)")
        return self


class DashboardSlide(SlideBase):
    type: Literal["dashboard"] = "dashboard"
    title: str = Field(min_length=1)
    subtitle: Optional[str] = None
    metrics: List[MetricCard] = Field(default_factory=list, min_length=1)
    chart: Optional[ChartSpec] = None
    bullets: List[BulletItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _limit(self) -> "DashboardSlide":
        if len(self.metrics) > MAX_DASHBOARD_METRICS:
            raise ValueError(f"Too many dashboard metrics ({len(self.metrics)})")
        return self


class SwoSlide(SlideBase):
    type: Literal["swot"] = "swot"
    title: str = Field(min_length=1)
    strengths: SwoQuadrant = Field(default_factory=SwoQuadrant)
    weaknesses: SwoQuadrant = Field(default_factory=SwoQuadrant)
    opportunities: SwoQuadrant = Field(default_factory=SwoQuadrant)
    threats: SwoQuadrant = Field(default_factory=SwoQuadrant)
    context: Optional[str] = None

    @model_validator(mode="after")
    def _limit(self) -> "SwoSlide":
        for q in (self.strengths, self.weaknesses, self.opportunities, self.threats):
            if len(q.items) > MAX_SWOT_ITEMS:
                raise ValueError(f"Too many SWOT items in {q.title!r}")
        return self


class ConclusionSlide(SlideBase):
    type: Literal["conclusion"] = "conclusion"
    title: str = Field(min_length=1)
    takeaways: List[str] = Field(default_factory=list, min_length=1)
    cta: Optional[str] = None
    quote: Optional[str] = None

    @model_validator(mode="after")
    def _limit(self) -> "ConclusionSlide":
        if len(self.takeaways) > 6:
            raise ValueError("Too many takeaways")
        return self


Slide = Annotated[
    Union[
        TitleSlide,
        HeroSlide,
        AgendaSlide,
        BulletsSlide,
        ComparisonSlide,
        TimelineSlide,
        ProcessSlide,
        RoadmapSlide,
        CycleSlide,
        HierarchySlide,
        DashboardSlide,
        SwoSlide,
        ConclusionSlide,
    ],
    Field(discriminator="type"),
]


class PresentationMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    created_by: Optional[str] = None


class Presentation(BaseModel):
    """The root AST node.  Fully validated before it reaches the renderer."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    aspect: AspectRatio = AspectRatio.SIXTEEN_NINE
    theme: Optional[str] = None
    theme_spec: Optional[ThemeSpec] = None
    footer: Optional[str] = None
    meta: Optional[PresentationMeta] = None
    slides: List[Slide] = Field(default_factory=list, min_length=1)
