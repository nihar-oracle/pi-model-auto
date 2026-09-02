import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from datasets import Dataset
from huggingface_hub import hf_hub_download
from optimum.exporters.onnx import main_export
from onnxruntime.quantization import QuantType, quantize_dynamic
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

MODEL_ID = "anasnassar/llm-query-complexity-classifier"
MODEL_REVISION = "27f10a015a9513247c0aed0ccd72281b8befd119"
DATASET_ID = "anasnassar/llm-query-complexity-benchmark"
DATASET_REVISION = "e111dc811aea9103010db741db9af0505240e77c"
LABELS = ["LOW", "MEDIUM", "HIGH"]
LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}


def routing_metrics(expected: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    under = predicted < expected
    severe = predicted + 1 < expected
    high = expected == LABEL_TO_ID["HIGH"]
    return {
        "accuracy": float(accuracy_score(expected, predicted)),
        "macro_f1": float(f1_score(expected, predicted, average="macro")),
        "high_recall": float((predicted[high] == LABEL_TO_ID["HIGH"]).mean()),
        "underroute_rate": float(under.mean()),
        "severe_underroute_rate": float(severe.mean()),
    }


class CostSensitiveTrainer(Trainer):
    def __init__(self, *args, risk_lambda: float, **kwargs):
        super().__init__(*args, **kwargs)
        self.risk_lambda = risk_lambda

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        cross_entropy = F.cross_entropy(outputs.logits, labels)
        # Rows are true tiers; columns are routed tiers. Severe under-routing costs much more than
        # adjacent under-routing, while over-routing carries a smaller quality/cost penalty.
        costs = outputs.logits.new_tensor([
            [0.0, 0.15, 0.50],
            [1.0, 0.0, 0.15],
            [5.0, 1.0, 0.0],
        ])
        expected_routing_cost = (outputs.logits.softmax(dim=-1) * costs[labels]).sum(dim=-1).mean()
        loss = cross_entropy + self.risk_lambda * expected_routing_cost
        return (loss, outputs) if return_outputs else loss


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--risk-lambda", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)
    args.output.mkdir(parents=True, exist_ok=True)

    train_path = hf_hub_download(
        DATASET_ID,
        "train.jsonl",
        repo_type="dataset",
        revision=DATASET_REVISION,
    )
    records = [json.loads(line) for line in Path(train_path).read_text().splitlines() if line]
    train_rows, validation_rows = train_test_split(
        records,
        test_size=0.2,
        random_state=42,
        stratify=[row["ground_truth"] for row in records],
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION)

    def make_dataset(rows: list[dict]) -> Dataset:
        encoded = tokenizer(
            [row["text"] for row in rows],
            truncation=True,
            max_length=128,
        )
        encoded["labels"] = [LABEL_TO_ID[row["ground_truth"]] for row in rows]
        return Dataset.from_dict(encoded)

    train_dataset = make_dataset(train_rows)
    validation_dataset = make_dataset(validation_rows)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    checkpoint_dir = args.output / "checkpoints"
    training_args = TrainingArguments(
        output_dir=str(checkpoint_dir),
        learning_rate=2e-5,
        weight_decay=0.01,
        warmup_ratio=0.1,
        num_train_epochs=4,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=32,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
        load_best_model_at_end=True,
        metric_for_best_model="routing_score",
        greater_is_better=True,
        report_to=[],
        seed=42,
        data_seed=42,
    )

    def compute_metrics(result) -> dict[str, float]:
        expected = result.label_ids
        predicted = result.predictions.argmax(axis=-1)
        metrics = routing_metrics(expected, predicted)
        metrics["routing_score"] = (
            metrics["macro_f1"]
            - 4.0 * metrics["severe_underroute_rate"]
            - 0.5 * metrics["underroute_rate"]
        )
        return metrics

    trainer = CostSensitiveTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        processing_class=tokenizer,
        compute_metrics=compute_metrics,
        risk_lambda=args.risk_lambda,
    )
    trainer.train()
    validation_metrics = trainer.evaluate()

    best_dir = args.output / "best"
    trainer.save_model(best_dir)
    tokenizer.model_max_length = 128
    tokenizer.save_pretrained(best_dir)

    full_onnx_dir = args.output / "onnx-full"
    main_export(
        model_name_or_path=str(best_dir),
        output=full_onnx_dir,
        task="text-classification",
        opset=17,
    )
    export_dir = args.output / "classifier"
    (export_dir / "onnx").mkdir(parents=True, exist_ok=True)
    for name in ["config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"]:
        source = best_dir / name
        if source.exists():
            (export_dir / name).write_bytes(source.read_bytes())
    quantize_dynamic(
        str(full_onnx_dir / "model.onnx"),
        str(export_dir / "onnx" / "model_quantized.onnx"),
        weight_type=QuantType.QInt8,
    )
    metadata = {
        "risk_lambda": args.risk_lambda,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "dataset_id": DATASET_ID,
        "dataset_revision": DATASET_REVISION,
        "seed": 42,
        "train_records": len(train_rows),
        "validation_records": len(validation_rows),
        "validation": validation_metrics,
    }
    (args.output / "metrics.json").write_text(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
