type LogContext = Record<string, unknown>;

function serializeContext(context?: LogContext): string {
  if (!context) {
    return "";
  }
  return ` ${JSON.stringify(context)}`;
}

export function logInfo(message: string, context?: LogContext): void {
  console.log(`[INFO] ${message}${serializeContext(context)}`);
}

export function logError(message: string, context?: LogContext): void {
  console.error(`[ERROR] ${message}${serializeContext(context)}`);
}
