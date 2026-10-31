/** Fail closed: frontend development mode alone says nothing about database isolation. */
export function localIdentityEnabled(
  environment: Record<string, string | undefined> = process.env,
): boolean {
  if (environment["LOCAL_DEV_AUTH"] !== "true") return false;
  if (
    environment["APP_ENV"] !== "local" ||
    environment["NODE_ENV"] !== "development" ||
    environment["BACKEND_ORIGIN"] !== "http://backend:8000"
  ) {
    throw new Error("Local identity requires isolated local development, not live or production.");
  }
  return true;
}
