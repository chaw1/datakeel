import { post } from "./client";

import type { components } from "./generated";
import type { ActionPlan } from "./types";

export type TrainingRun = components["schemas"]["TrainingGovernanceRun"];
export type TrainingReport = components["schemas"]["TrainingReport"];
export type TrainingRecord = components["schemas"]["TrainingRecord"];
export type TrainingConfig = components["schemas"]["TrainingConfig"];
export type TrainingEvaluation = components["schemas"]["TrainingEvaluation"];
export type AnalysisRequest = Omit<
  Partial<components["schemas"]["TrainingAnalysisRequest"]>,
  "config"
> & { config?: Partial<TrainingConfig> };
type EvaluationRequest = components["schemas"]["TrainingEvaluationRequest"];

export function trainingPath(datasetId: string) {
  return `/api/datasets/${encodeURIComponent(datasetId)}/text-governance`;
}

export function analyzeTraining(datasetId: string, body: AnalysisRequest) {
  return post<TrainingRun>(`${trainingPath(datasetId)}/analyze`, body);
}

export function registerEvaluation(datasetId: string, body: EvaluationRequest) {
  return post<TrainingEvaluation>(
    `${trainingPath(datasetId)}/evaluations`,
    body,
  );
}

export function prepareTrainingClean(runId: string) {
  return post<ActionPlan>(
    `/api/training-governance/${encodeURIComponent(runId)}/clean`,
    {},
  );
}
