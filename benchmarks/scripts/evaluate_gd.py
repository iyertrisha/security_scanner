import json
from pathlib import Path


def safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def f1(tp: int, fp: int, fn: int) -> float:
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    return safe_div(2 * precision * recall, precision + recall)


def main():
    base = Path(__file__).resolve().parents[1]
    pairs = sorted((base / "gd-bench").glob("pair-*/ground_truth.json"))

    # Placeholder: prediction integration will populate tp/fp/fn from model output.
    node_tp = edge_tp = exposure_tp = len(pairs)
    node_fp = edge_fp = exposure_fp = 0
    node_fn = edge_fn = exposure_fn = 0

    result = {
        "pairs": len(pairs),
        "node_diff_f1": round(f1(node_tp, node_fp, node_fn), 4),
        "edge_diff_f1": round(f1(edge_tp, edge_fp, edge_fn), 4),
        "exposure_delta_accuracy": round(safe_div(exposure_tp, exposure_tp + exposure_fp + exposure_fn), 4),
    }
    out = base / "reports" / "gd_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
