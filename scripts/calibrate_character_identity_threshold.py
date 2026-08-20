"""Calibrate character identity threshold from labelled JSONL text pairs.

Each line: {"left_text": "...", "right_text": "...", "same_identity": true}
"""

import argparse
import json
from pathlib import Path

from services.application.app.analysis.character_threshold import calibrate_threshold
from services.application.app.indexing.embedding import RemoteEmbeddingProvider
from services.application.app.indexing.service import _cosine_similarity


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--embedding-url", required=True)
    args = parser.parse_args()
    embedding = RemoteEmbeddingProvider(base_url=args.embedding_url)
    samples = []
    rows = []
    for line_number, line in enumerate(Path(args.input).read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        score = _cosine_similarity(
            embedding.embed(row["left_text"]), embedding.embed(row["right_text"])
        )
        label = row["same_identity"]
        if not isinstance(label, bool):
            raise ValueError(f"line {line_number}: same_identity must be boolean")
        samples.append((score, label))
        rows.append({"line": line_number, "score": score, "same_identity": label})
    result = calibrate_threshold(tuple(samples))
    print(json.dumps({
        "recommended_threshold": result.threshold,
        "balanced_accuracy": result.balanced_accuracy,
        "confusion": {
            "true_positive": result.true_positive,
            "false_positive": result.false_positive,
            "true_negative": result.true_negative,
            "false_negative": result.false_negative,
        },
        "samples": rows,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
