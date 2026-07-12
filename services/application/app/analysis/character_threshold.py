"""Deterministic threshold selection for labelled character-pair scores."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThresholdMetrics:
    threshold: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int

    @property
    def balanced_accuracy(self) -> float:
        positive = self.true_positive + self.false_negative
        negative = self.true_negative + self.false_positive
        tpr = self.true_positive / positive if positive else 0.0
        tnr = self.true_negative / negative if negative else 0.0
        return (tpr + tnr) / 2


def calibrate_threshold(samples: tuple[tuple[float, bool], ...]) -> ThresholdMetrics:
    if not samples or not any(label for _, label in samples) or not any(
        not label for _, label in samples
    ):
        raise ValueError("calibration requires both identity labels")
    candidates = sorted({score for score, _ in samples}, reverse=True)
    metrics = tuple(_metrics(samples, threshold) for threshold in candidates)
    # Prefer the stricter (higher) threshold on equal balanced accuracy.
    return max(metrics, key=lambda item: (item.balanced_accuracy, item.threshold))


def _metrics(samples, threshold):
    tp = fp = tn = fn = 0
    for score, same_identity in samples:
        predicted_same = score >= threshold
        if predicted_same and same_identity:
            tp += 1
        elif predicted_same:
            fp += 1
        elif same_identity:
            fn += 1
        else:
            tn += 1
    return ThresholdMetrics(threshold, tp, fp, tn, fn)
