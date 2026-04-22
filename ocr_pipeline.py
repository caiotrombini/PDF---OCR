#!/usr/bin/env python3
"""Pipeline OCR rápido para gerar PDF pesquisável.

Requisitos externos (binários no PATH):
- ocrmypdf
- ghostscript (gs) [opcional, usado para reduzir DPI]
- pdftotext [opcional, usado para detectar PDF nativo]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class RunConfig:
    mode: str
    lang: str
    workers: int
    fallback: str
    force_ocr: bool
    dpi_fast: int


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True)


def has_text_layer(pdf: Path) -> bool:
    """Detecta texto nativo usando pdftotext quando disponível."""
    if shutil.which("pdftotext") is None:
        return False
    proc = run_cmd(["pdftotext", str(pdf), "-"])
    if proc.returncode != 0:
        return False
    return len(proc.stdout.strip()) > 40


def downsample_pdf(input_pdf: Path, output_pdf: Path, dpi: int) -> None:
    """Reduz resolução para acelerar OCR."""
    gs = shutil.which("gs")
    if gs is None:
        shutil.copy2(input_pdf, output_pdf)
        return

    cmd = [
        gs,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dNOPAUSE",
        "-dBATCH",
        "-dQUIET",
        "-dDownsampleColorImages=true",
        "-dColorImageDownsampleType=/Bicubic",
        f"-dColorImageResolution={dpi}",
        "-dDownsampleGrayImages=true",
        "-dGrayImageDownsampleType=/Bicubic",
        f"-dGrayImageResolution={dpi}",
        "-dDownsampleMonoImages=true",
        "-dMonoImageDownsampleType=/Subsample",
        f"-dMonoImageResolution={dpi}",
        f"-sOutputFile={output_pdf}",
        str(input_pdf),
    ]
    proc = run_cmd(cmd)
    if proc.returncode != 0:
        shutil.copy2(input_pdf, output_pdf)


def ocrmypdf_args(mode: str, lang: str, workers: int, input_pdf: Path, output_pdf: Path) -> list[str]:
    args = [
        "ocrmypdf",
        "--skip-text",
        "--jobs",
        str(max(1, workers)),
        "--language",
        lang,
        "--output-type",
        "pdf",
        "--quiet",
    ]

    # Perfil de performance por modo.
    if mode == "fast":
        args += ["--optimize", "0", "--tesseract-timeout", "60", "--fast-web-view", "999999"]
    elif mode == "balanced":
        args += ["--optimize", "1", "--tesseract-timeout", "120"]
    else:  # accurate
        args += ["--optimize", "2", "--tesseract-timeout", "180", "--deskew", "--clean"]

    args += [str(input_pdf), str(output_pdf)]
    return args


def process_one(pdf: Path, out_dir: Path, cfg: RunConfig) -> dict:
    t0 = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = out_dir / pdf.name

    if output_pdf.exists():
        return {
            "file": str(pdf),
            "status": "skipped_exists",
            "seconds": 0.0,
            "output": str(output_pdf),
        }

    if not cfg.force_ocr and has_text_layer(pdf):
        shutil.copy2(pdf, output_pdf)
        return {
            "file": str(pdf),
            "status": "copied_text_native",
            "seconds": time.perf_counter() - t0,
            "output": str(output_pdf),
        }

    with tempfile.TemporaryDirectory(prefix="ocrtmp_") as td:
        work_input = Path(td) / "input.pdf"
        if cfg.mode == "fast":
            downsample_pdf(pdf, work_input, cfg.dpi_fast)
        else:
            shutil.copy2(pdf, work_input)

        cmd = ocrmypdf_args(cfg.mode, cfg.lang, cfg.workers, work_input, output_pdf)
        proc = run_cmd(cmd)
        status = "ok" if proc.returncode == 0 else "error"

        # Fallback simples: reprocessar no modo balanced se fast falhar.
        if status == "error" and cfg.fallback != "off" and cfg.mode == "fast":
            cmd_fb = ocrmypdf_args("balanced", cfg.lang, max(1, cfg.workers // 2), work_input, output_pdf)
            fb = run_cmd(cmd_fb)
            if fb.returncode == 0:
                status = "ok_fallback"

    return {
        "file": str(pdf),
        "status": status,
        "seconds": round(time.perf_counter() - t0, 3),
        "output": str(output_pdf),
    }


def iter_pdfs(path: Path) -> Iterable[Path]:
    if path.is_file() and path.suffix.lower() == ".pdf":
        yield path
        return
    for p in sorted(path.glob("*.pdf")):
        if p.is_file():
            yield p


def command_process(args: argparse.Namespace) -> int:
    src = Path(args.input).expanduser().resolve()
    out = Path(args.output).expanduser().resolve()
    pdfs = list(iter_pdfs(src))
    if not pdfs:
        print("Nenhum PDF encontrado.")
        return 1

    cfg = RunConfig(
        mode=args.mode,
        lang=args.lang,
        workers=args.workers,
        fallback=args.fallback,
        force_ocr=args.force_ocr,
        dpi_fast=args.dpi_fast,
    )

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(process_one, pdf, out, cfg) for pdf in pdfs]
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            print(f"[{res['status']}] {res['file']} -> {res['output']} ({res['seconds']}s)")

    summary = {
        "count": len(results),
        "ok": sum(1 for r in results if r["status"].startswith("ok") or r["status"].startswith("copied")),
        "errors": sum(1 for r in results if "error" in r["status"]),
        "total_seconds": round(sum(float(r["seconds"]) for r in results), 3),
        "mode": args.mode,
        "dpi_fast": args.dpi_fast,
    }
    out.mkdir(parents=True, exist_ok=True)
    summary_file = out / "run_summary.json"
    summary_file.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    print(f"\nResumo salvo em: {summary_file}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["errors"] == 0 else 2


def command_benchmark(args: argparse.Namespace) -> int:
    # Benchmark simples usando o próprio process.
    ns = argparse.Namespace(**vars(args))
    ns.output = args.output
    rc = command_process(ns)
    print("Benchmark concluído. Veja run_summary.json para tempo por arquivo.")
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pipeline OCR rápido com modo fast (DPI reduzido)")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("input", help="PDF ou pasta com PDFs")
    common.add_argument("-o", "--output", required=True, help="Pasta de saída")
    common.add_argument("--mode", choices=["fast", "balanced", "accurate"], default="fast")
    common.add_argument("--lang", default="por")
    common.add_argument("--workers", type=int, default=4)
    common.add_argument("--fallback", choices=["off", "balanced"], default="balanced")
    common.add_argument("--force-ocr", action="store_true")
    common.add_argument("--dpi-fast", type=int, default=120, help="DPI para downsample no modo fast")

    sp = sub.add_parser("process", parents=[common], help="Processa PDF(s)")
    sp.set_defaults(func=command_process)

    sb = sub.add_parser("benchmark", parents=[common], help="Benchmark rápido")
    sb.set_defaults(func=command_benchmark)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
