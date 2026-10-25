"""Command-line entry point: documind-eval."""

import argparse
import json
import sys
from pathlib import Path

from .invoice_eval import evaluate_manifest as evaluate_invoices
from .manifest import KNOWN_TASKS, ManifestError, load_manifest
from .ocr_eval import evaluate_manifest as evaluate_ocr
from .report import render_markdown
from .table_eval import evaluate_manifest as evaluate_tables

EVALUATORS = {"ocr": evaluate_ocr, "invoice": evaluate_invoices,
              "table": evaluate_tables}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="documind-eval",
        description=(
            "Evaluate saved prediction files against labeled ground truth "
            "using a manifest. Runs without OCR inference: predictions must "
            "already be saved."
        ),
    )
    parser.add_argument(
        "--task", choices=KNOWN_TASKS, default=None,
        help="Evaluation task (defaults to the manifest's task field)",
    )
    parser.add_argument("--manifest", required=True, help="Manifest JSON path")
    parser.add_argument(
        "--output", default=None,
        help="Output directory for summary.json and report.md "
             "(default: outputs/eval/<task>)",
    )
    parser.add_argument(
        "--case-sensitive", action="store_true",
        help="Disable casefold in text comparisons (OCR/table tasks)",
    )
    parser.add_argument(
        "--preserve-whitespace", action="store_true",
        help="Disable whitespace collapsing in text comparisons (OCR task)",
    )
    return parser


def run_eval(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    task = args.task or manifest.task
    if args.task and args.task != manifest.task:
        raise ManifestError(
            f"--task {args.task!r} contradicts manifest task {manifest.task!r}"
        )

    kwargs = {}
    if task == "ocr":
        # Table normalization is fixed by spec; only OCR exposes toggles.
        kwargs = {
            "casefold": not args.case_sensitive,
            "collapse_whitespace": not args.preserve_whitespace,
        }

    summary = EVALUATORS[task](manifest, **kwargs)
    output_dir = Path(args.output) if args.output else Path("outputs") / "eval" / task
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report_path.write_text(render_markdown(summary), encoding="utf-8")

    print(f"Task: {task} | documents: {len(manifest.entries)}")
    aggregate = summary["aggregate"]
    if task == "ocr":
        print(f"CER {aggregate['cer']:.4f} | WER {aggregate['wer']:.4f}")
    elif task == "invoice":
        print(
            f"micro field accuracy {aggregate['micro_field_accuracy']} | "
            f"macro {aggregate['macro_field_accuracy']}"
        )
    else:
        print(
            f"cell exact agreement {aggregate['cell_exact_agreement']} | "
            f"tables {aggregate['tables_matched_pairs']}/"
            f"{aggregate['tables_expected']}"
        )
    print(f"Summary: {summary_path}")
    print(f"Report:  {report_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_eval(args)
    except (ManifestError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Evaluation error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
