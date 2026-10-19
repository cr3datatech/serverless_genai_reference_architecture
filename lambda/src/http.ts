import type { APIGatewayProxyResult } from "aws-lambda";

/**
 * An error that is safe to show to the client. Anything else is reported as
 * a generic internal error, so raw Bedrock or runtime messages never leak
 * (BUILD_PLAN.md API contract).
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly type: string,
    message: string,
  ) {
    super(message);
  }
}

export function json(status: number, body: unknown, requestId: string): APIGatewayProxyResult {
  return {
    statusCode: status,
    headers: { "content-type": "application/json", "x-request-id": requestId },
    body: JSON.stringify(body),
  };
}

export function errorResponse(err: ApiError, requestId: string): APIGatewayProxyResult {
  return json(err.status, { error: { type: err.type, message: err.message, request_id: requestId } }, requestId);
}

/**
 * Maps Bedrock and runtime failures to client-safe errors. Throttling becomes
 * 429 so well-behaved clients back off and retry (Reliability).
 */
export function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  const name = e instanceof Error ? e.name : "";
  switch (name) {
    case "ThrottlingException":
    case "ServiceQuotaExceededException":
      return new ApiError(429, "rate_limited", "The model is busy. Retry with exponential backoff.");
    case "ValidationException":
      return new ApiError(400, "invalid_request", "The model rejected the request parameters.");
    case "AccessDeniedException":
    case "ResourceNotFoundException":
      return new ApiError(503, "model_unavailable", "The requested model is not available in this deployment.");
    case "ModelTimeoutException":
    case "TimeoutError":
    case "AbortError":
      return new ApiError(504, "timeout", "The model did not respond in time. Try a smaller max_tokens or a faster model.");
    case "ServiceUnavailableException":
    case "ModelNotReadyException":
    case "ModelErrorException":
    case "InternalServerException":
      return new ApiError(502, "upstream_error", "The model service returned an error. Retry later.");
    default:
      return new ApiError(500, "internal_error", "Internal error.");
  }
}
