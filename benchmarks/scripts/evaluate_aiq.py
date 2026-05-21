import json
from pathlib import Path


DIMENSIONS = [
    "accuracy",
    "specificity",
    "blast_radius_correctness",
    "actionability",
    "calibration",
]


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else 0.0


def main():
    base = Path(__file__).resolve().parents[1]
    annotation_dir = base / "aiq-bench" / "human_annotations"
    files = sorted(annotation_dir.glob("*.json"))
    scores = {dim: [] for dim in DIMENSIONS}

    for file_path in files:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        row = payload.get("scores", {})
        for dim in DIMENSIONS:
            scores[dim].append(row.get(dim))

    result = {
        "samples": len(files),
        "means": {dim: round(mean(values), 4) for dim, values in scores.items()},
        "cohens_kappa": None,
        "notes": "Add dual-annotator labels to compute Cohen's kappa.",
    }
    out = base / "reports" / "aiq_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
