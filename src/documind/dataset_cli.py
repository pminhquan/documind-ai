"""Command-line entry point: documind-dataset.

Onboarding and validation run anywhere; ``predict`` runs the existing
local pipelines (PaddleOCR) and is intended for the developer machine,
never for CI.
"""

import argparse
import sys
from pathlib import Path

from .dataset import (
    DATASET_README,
    TASKS,
    DatasetError,
    add_document,
    annotated_document_ids,
    dataset_root,
    find_document_image,
    init_dataset,
    validate_dataset,
    write_task_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="documind-dataset",
        description=(
            "Onboard, validate, and run predictions for a local "
            "real-document evaluation dataset. Raw and anonymized data "
            "stay out of Git; ground truth is always annotated manually."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create the dataset layout")
    init_parser.add_argument("--root", default=None, help="dataset root directory")

    add_parser = subparsers.add_parser("add", help="register an anonymized image")
    add_parser.add_argument("image", help="path to the (anonymized) source image")
    add_parser.add_argument("--id", required=True, dest="document_id",
                            help="document id used in annotations and manifests")
    add_parser.add_argument("--root", default=None, help="dataset root directory")
    add_parser.add_argument(
        "--confirm-anonymized", action="store_true",
        help="assert that personal data was removed from the image",
    )

    validate_parser = subparsers.add_parser(
        "validate", help="check structure and annotation completeness"
    )
    validate_parser.add_argument("--root", default=None, help="dataset root directory")

    predict_parser = subparsers.add_parser(
        "predict", help="run the local pipelines on annotated documents"
    )
    predict_parser.add_argument("--task", required=True, choices=TASKS)
    predict_parser.add_argument("--root", default=None, help="dataset root directory")
    return parser


def _predict_task(task: str, root: str | None) -> int:
    """Run the local pipelines on annotated documents.

    OCR predictions are regenerated on every run (including the OCR step
    of invoice prediction) so a modified source image can never silently
    reuse a stale OCR output. Ground truth files are never touched.
    """
    base = dataset_root(root)
    document_ids = annotated_document_ids(base, task)
    if not document_ids:
        print(f"No annotated documents for task '{task}' — nothing to predict.")
        return 0

    from .cli import main as ocr_main
    from .extract_cli import main as extract_main
    from .table_cli import main as table_main

    failures: list[str] = []
    for document_id in document_ids:
        image = find_document_image(base, document_id)
        if image is None:
            failures.append(f"{document_id}: anonymized image not found")
            continue
        if task == "ocr":
            output = base / "predictions" / f"{document_id}.ocr.json"
            exit_code = ocr_main([str(image), "-o", str(output), "--compact"])
        elif task == "table":
            output = base / "predictions" / f"{document_id}.tables.json"
            exit_code = table_main([str(image), "-o", str(output), "--compact"])
        else:  # invoice: OCR is regenerated fresh, then extraction runs on it
            ocr_output = base / "predictions" / f"{document_id}.ocr.json"
            if ocr_main([str(image), "-o", str(ocr_output), "--compact"]) != 0:
                failures.append(f"{document_id}: OCR step failed")
                continue
            output = base / "predictions" / f"{document_id}.invoice.json"
            exit_code = extract_main([str(ocr_output), "-o", str(output)])
        if exit_code != 0:
            failures.append(f"{document_id}: pipeline exited with {exit_code}")
        else:
            print(f"  predicted {document_id} -> {output.name}")

    manifest_path = write_task_manifest(base, task)
    print(f"Manifest written: {manifest_path}")
    if failures:
        for failure in failures:
            print(f"ERROR {failure}", file=sys.stderr)
        return 1
    print(
        f"Next: documind-eval --task {task} --manifest "
        f"{Path(manifest_path).as_posix()} --output reports/eval/{task}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            base = init_dataset(args.root)
            print(f"Dataset initialized at: {base}")
            print(DATASET_README)
            return 0
        if args.command == "add":
            target = add_document(args.image, args.document_id,
                                  root=args.root,
                                  confirm_anonymized=args.confirm_anonymized)
            print(f"Document registered: {target}")
            print(
                "Next: annotate ground truth into ground_truth/"
                f"{args.document_id}.<ocr|invoice|table>.json, then run "
                "'documind-dataset validate'."
            )
            return 0
        if args.command == "validate":
            ok, lines = validate_dataset(args.root)
            print("\n".join(lines))
            return 0 if ok else 1
        if args.command == "predict":
            return _predict_task(args.task, args.root)
    except DatasetError as exc:
        print(f"Dataset error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"IO error: {exc}", file=sys.stderr)
        return 1
    print(f"unknown command {args.command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
