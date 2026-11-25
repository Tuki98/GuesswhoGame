import { ApiError } from "@/api/client";

export class SessionExpiredError extends Error {
  constructor(message = "Your session has expired. Join the room again.") {
    super(message);
    this.name = "SessionExpiredError";
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof SessionExpiredError) {
    return error.message;
  }
  if (error instanceof ApiError) {
    return error.userMessage;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Something went wrong. Please try again.";
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
