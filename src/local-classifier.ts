import { env, pipeline, type TextClassificationPipeline } from "@huggingface/transformers";
import { fileURLToPath } from "node:url";

export type LocalComplexityLabel = "LOW" | "MEDIUM" | "HIGH";
export interface LocalClassification {
  label: LocalComplexityLabel;
  scores: Record<LocalComplexityLabel, number>;
}

type PipelineRow = { label: string; score: number };

let classifierPromise: Promise<TextClassificationPipeline> | undefined;

function classifier() {
  if (classifierPromise) return classifierPromise;

  const modelRoot = process.env.PI_MODEL_AUTO_CLASSIFIER_ROOT ??
    fileURLToPath(new URL("../models/complexity-classifier", import.meta.url));
  env.allowRemoteModels = false;
  env.allowLocalModels = true;
  classifierPromise = pipeline("text-classification", modelRoot, { dtype: "q8" }).catch((error) => {
    classifierPromise = undefined;
    throw error;
  });
  return classifierPromise;
}

export async function warmLocalClassifier(): Promise<void> {
  await classifier();
}

export async function classifyLocally(text: string): Promise<LocalClassification> {
  const run = await classifier();
  const rows = await run(text, { top_k: 3 }) as unknown as PipelineRow[];
  const scores: Record<LocalComplexityLabel, number> = { LOW: 0, MEDIUM: 0, HIGH: 0 };
  for (const row of rows) {
    const label = row.label.toUpperCase() as LocalComplexityLabel;
    if (label in scores) scores[label] = row.score;
  }
  const best = (Object.entries(scores) as [LocalComplexityLabel, number][])
    .reduce((currentBest, current) => current[1] > currentBest[1] ? current : currentBest);
  // Frozen on the public training split. Ambiguous prompts fail upward rather than under-route.
  const label = best[1] < 0.45 ? "HIGH" : best[0];
  return { label, scores };
}
