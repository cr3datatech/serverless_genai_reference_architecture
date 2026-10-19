// Runtime configuration, read once per execution environment from the
// environment variables Terraform sets (terraform/lambda.tf). Model aliases
// and prices are configuration, not code (BUILD_PLAN.md D5, D7).

export interface ModelConfig {
  /** Application inference profile ARN the function invokes. */
  arn: string;
  /** System-defined inference profile behind the alias, shown to clients. */
  modelId: string;
  /** USD per million input / output tokens; null disables the cost estimate. */
  inputPerMtok: number | null;
  outputPerMtok: number | null;
}

export interface Config {
  models: Record<string, ModelConfig>;
  defaultModel: string;
  maxTokensCap: number;
  maxBodyBytes: number;
  bedrockTimeoutMs: number;
  metricsNamespace: string;
}

function intFromEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  const value = raw === undefined ? fallback : Number(raw);
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
}

export function loadConfig(): Config {
  const models = JSON.parse(process.env.MODELS ?? "{}") as Record<string, ModelConfig>;
  const defaultModel = process.env.DEFAULT_MODEL ?? "fast";
  if (!(defaultModel in models)) {
    throw new Error(`DEFAULT_MODEL "${defaultModel}" is not one of the configured aliases`);
  }
  return {
    models,
    defaultModel,
    maxTokensCap: intFromEnv("MAX_TOKENS_CAP", 1024),
    maxBodyBytes: intFromEnv("MAX_BODY_BYTES", 65536),
    bedrockTimeoutMs: intFromEnv("BEDROCK_TIMEOUT_MS", 25000),
    metricsNamespace: process.env.METRICS_NAMESPACE ?? "PowerLab/GenAIApi",
  };
}
