// CloudWatch Embedded Metric Format (EMF), BUILD_PLAN.md D7.
//
// Adding an `_aws` block to a JSON log line tells CloudWatch Logs to turn the
// named fields into metrics. No PutMetricData call, no extra permission, no
// extra latency: the log line and the metrics are the same write.
// https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html

export interface ModelCallMetrics {
  InputTokens: number;
  OutputTokens: number;
  /** Omitted when no prices are configured for the alias. */
  CostUSD?: number;
  ModelLatency?: number;
}

const UNITS: Record<keyof ModelCallMetrics, string> = {
  InputTokens: "Count",
  OutputTokens: "Count",
  CostUSD: "None",
  ModelLatency: "Milliseconds",
};

/**
 * Fields to merge into the request's log line so that CloudWatch records
 * the model call's metrics, with the alias as the only dimension. Few
 * metrics and one dimension keep the custom-metric bill small (Cost).
 */
export function modelCallMetrics(namespace: string, alias: string, values: ModelCallMetrics): Record<string, unknown> {
  const present = (Object.keys(values) as (keyof ModelCallMetrics)[]).filter((k) => values[k] !== undefined);
  return {
    _aws: {
      Timestamp: Date.now(),
      CloudWatchMetrics: [
        {
          Namespace: namespace,
          Dimensions: [["Model"]],
          Metrics: present.map((name) => ({ Name: name, Unit: UNITS[name] })),
        },
      ],
    },
    Model: alias,
    ...Object.fromEntries(present.map((k) => [k, values[k]])),
  };
}
