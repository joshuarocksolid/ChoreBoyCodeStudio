from __future__ import annotations

import argparse
import json
import os
import time
from typing import Dict, List

from jasper_bridge import Report


def run_profile(
    jrxml: str,
    output_dir: str,
    iterations: int,
    zoom: float,
    jdbc: str = None,
    user: str = None,
    password: str = None,
) -> Dict[str, object]:
    os.makedirs(output_dir, exist_ok=True)
    timings: List[Dict[str, float]] = []

    for index in range(iterations):
        report = Report(jrxml)

        fill_start = time.perf_counter()
        report.fill(jdbc=jdbc, user=user, password=password)
        fill_elapsed = time.perf_counter() - fill_start

        pdf_path = os.path.join(output_dir, "run_{:03d}.pdf".format(index + 1))
        pdf_start = time.perf_counter()
        report.export_pdf(pdf_path, overwrite=True)
        pdf_elapsed = time.perf_counter() - pdf_start

        png_dir = os.path.join(output_dir, "run_{:03d}_pages".format(index + 1))
        png_start = time.perf_counter()
        page_paths = report.export_png(png_dir, zoom=zoom, overwrite=True)
        png_elapsed = time.perf_counter() - png_start

        timings.append(
            {
                "fill_seconds": fill_elapsed,
                "pdf_seconds": pdf_elapsed,
                "png_seconds": png_elapsed,
                "page_count": float(len(page_paths)),
            }
        )

    def avg(key: str) -> float:
        return sum(item[key] for item in timings) / float(len(timings))

    return {
        "iterations": iterations,
        "jrxml": os.path.abspath(jrxml),
        "output_dir": os.path.abspath(output_dir),
        "average_fill_seconds": avg("fill_seconds"),
        "average_pdf_seconds": avg("pdf_seconds"),
        "average_png_seconds": avg("png_seconds"),
        "average_page_count": avg("page_count"),
        "runs": timings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jrxml", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--zoom", type=float, default=2.0)
    parser.add_argument("--jdbc")
    parser.add_argument("--user")
    parser.add_argument("--password")
    args = parser.parse_args()

    summary = run_profile(
        jrxml=args.jrxml,
        output_dir=args.output_dir,
        iterations=max(args.iterations, 1),
        zoom=args.zoom,
        jdbc=args.jdbc,
        user=args.user,
        password=args.password,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
