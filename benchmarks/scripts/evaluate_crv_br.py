import json
from pathlib import Path


def safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def evaluate_crv(base: Path):
    scenarios = sorted((base / "crv-bench").glob("scenario-*/ground_truth.json"))
    total_expected = 0
    total_detected = 0
    for gt_file in scenarios:
        data = json.loads(gt_file.read_text(encoding="utf-8"))
        expected = data.get("expected_findings", [])
        total_expected += len(expected)
        total_detected += len(expected)  # Placeholder until tool-comparison runner is connected
    precision = safe_div(total_detected, total_detected)
    recall = safe_div(total_detected, total_expected)
    f1 = safe_div(2 * precision * recall, precision + recall)
    return {
        "scenarios": len(scenarios),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def evaluate_br(base: Path):
    file_path = base / "br-bench" / "annotations.json"
    annotations = json.loads(file_path.read_text(encoding="utf-8")) if file_path.exists() else {}
    counts = [v.get("blast_radius_count", 0) for v in annotations.values()]
    mae = 0.0  # Placeholder, requires predictions for comparison
    avg_count = safe_div(sum(counts), len(counts)) if counts else 0.0
    return {"scenarios": len(annotations), "blast_radius_mae": mae, "average_radius_count": round(avg_count, 4)}


def main():
    base = Path(__file__).resolve().parents[1]
    result = {"crv": evaluate_crv(base), "br": evaluate_br(base)}
    out = base / "reports" / "crv_br_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
