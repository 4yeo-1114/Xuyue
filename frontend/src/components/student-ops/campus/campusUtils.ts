export function cap(s: string): string {
  if (!s) return "";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function failureMsg(
  failures: { studentName?: string; reason: string }[],
): string {
  return failures.map((f) => `${f.studentName || ""} ${f.reason}`).join("；");
}
