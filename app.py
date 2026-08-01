"""ppt-ai command-line interface.

Commands
--------
generate   topic                 Create a deck from a topic (AI or offline).
ast        topic                 Emit only the Presentation AST as JSON.
build      ast.json              Render an AST JSON file into a .pptx.
sample                           Build a complete sample deck.
templates                        List available slide templates.
themes                           List available themes.
validate   deck.pptx             Validate a rendered deck.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import DEFAULT_OUTPUT, DEFAULT_THEME


def _build_ast(args) -> None:
    from ai.validator import JSONParseError, strict_parse
    from renderer import PresentationRenderer
    from validator import validate_presentation

    path = Path(args.input)
    raw = path.read_text(encoding="utf-8")
    try:
        ast = strict_parse(raw)
    except JSONParseError as exc:
        print(f"[error] invalid AST: {exc.message}", file=sys.stderr)
        sys.exit(2)
    if args.theme:
        ast.theme = args.theme
    report = validate_presentation(ast)
    if not report.ok:
        print("[warnings]")
        print(report)
    renderer = PresentationRenderer()
    out = renderer.render(ast, args.output)
    print(f"Wrote {out} ({len(ast.slides)} slides)")
    if args.validate:
        _validate_file(str(out))


def _generate(args) -> None:
    from ai.planner import Planner
    from renderer import PresentationRenderer
    from validator import validate_presentation

    sections = args.sections.split(",") if args.sections else None
    planner = Planner(mode=args.mode, model_name=args.model)
    ast = planner.plan(args.topic, sections=sections, tone=args.tone)

    if args.aspect:
        ast.aspect = args.aspect  # type: ignore[assignment]
    if args.theme:
        ast.theme = args.theme

    report = validate_presentation(ast)
    if not report.ok:
        print("[warnings]")
        print(report)

    if args.json:
        (Path(args.output).with_suffix(".json")).write_text(
            ast.model_dump_json(indent=2), encoding="utf-8")
        print(f"Wrote AST JSON to {Path(args.output).with_suffix('.json')}")
        return

    renderer = PresentationRenderer()
    out = renderer.render(ast, args.output)
    print(f"Wrote {out} ({len(ast.slides)} slides, theme={ast.theme or 'default'})")
    if args.validate:
        _validate_file(str(out))


def _ast(args) -> None:
    from ai.planner import Planner

    sections = args.sections.split(",") if args.sections else None
    planner = Planner(mode=args.mode, model_name=args.model)
    ast = planner.plan(args.topic, sections=sections, tone=args.tone)
    if args.theme:
        ast.theme = args.theme
    text = ast.model_dump_json(indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)


def _sample(args) -> None:
    from ai.planner import DeterministicPlanner
    from renderer import PresentationRenderer

    ast = DeterministicPlanner().build(args.topic)
    if args.theme:
        ast.theme = args.theme
    out = PresentationRenderer().render(ast, args.output)
    print(f"Wrote sample deck to {out} ({len(ast.slides)} slides)")


def _templates(_args) -> None:
    import templates  # noqa: F401  (registers templates)
    from templates.base import TemplateRegistry

    print("Available slide templates:")
    for kind in TemplateRegistry.kinds():
        print(f"  - {kind}")


def _themes(_args) -> None:
    from theme import Theme

    print("Available themes:")
    for name in Theme.list_builtin():
        print(f"  - {name}")


def _validate_file(path: str) -> None:
    from validator import LayoutValidator

    report = LayoutValidator().validate(path)
    print("[render validation]")
    if report.ok:
        print("OK")
    else:
        print(report)
    if not report.ok:
        sys.exit(1)


def _validate(args) -> None:
    _validate_file(args.input)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="ppt-ai",
                                     description="AI Presentation Generator / compiler")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="Generate a deck from a topic")
    p_gen.add_argument("topic")
    p_gen.add_argument("-o", "--output", default=DEFAULT_OUTPUT)
    p_gen.add_argument("--mode", choices=["auto", "ai", "deterministic"], default="auto")
    p_gen.add_argument("--model", default=None, help="HuggingFace model id or alias")
    p_gen.add_argument("--theme", default=None)
    p_gen.add_argument("--aspect", choices=["16:9", "16:10", "4:3"], default=None)
    p_gen.add_argument("--sections", default=None,
                       help="Comma-separated section names, e.g. title,bullets,process")
    p_gen.add_argument("--tone", default="professional")
    p_gen.add_argument("--json", action="store_true", help="Emit AST JSON instead of pptx")
    p_gen.add_argument("--validate", action="store_true")
    p_gen.set_defaults(func=_generate)

    p_ast = sub.add_parser("ast", help="Emit the Presentation AST as JSON")
    p_ast.add_argument("topic")
    p_ast.add_argument("-o", "--output", default=None)
    p_ast.add_argument("--mode", choices=["auto", "ai", "deterministic"], default="auto")
    p_ast.add_argument("--model", default=None)
    p_ast.add_argument("--theme", default=None)
    p_ast.add_argument("--sections", default=None)
    p_ast.add_argument("--tone", default="professional")
    p_ast.set_defaults(func=_ast)

    p_build = sub.add_parser("build", help="Render an AST JSON file to .pptx")
    p_build.add_argument("input", help="Path to AST JSON")
    p_build.add_argument("-o", "--output", default=DEFAULT_OUTPUT)
    p_build.add_argument("--theme", default=None)
    p_build.add_argument("--validate", action="store_true")
    p_build.set_defaults(func=_build_ast)

    p_sample = sub.add_parser("sample", help="Build a complete sample deck")
    p_sample.add_argument("-o", "--output", default="sample_deck.pptx")
    p_sample.add_argument("--topic", default="Digital Transformation")
    p_sample.add_argument("--theme", default=DEFAULT_THEME)
    p_sample.set_defaults(func=_sample)

    sub.add_parser("templates", help="List slide templates").set_defaults(func=_templates)
    sub.add_parser("themes", help="List themes").set_defaults(func=_themes)

    p_val = sub.add_parser("validate", help="Validate a rendered deck")
    p_val.add_argument("input")
    p_val.set_defaults(func=_validate)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
