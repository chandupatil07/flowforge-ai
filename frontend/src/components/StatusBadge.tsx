const COLORS: Record<string, string> = {
  QUEUED: "badge-blue",
  CLAIMED: "badge-purple",
  RUNNING: "badge-purple",
  COMPLETED: "badge-green",
  FAILED: "badge-red",
  CANCELLED: "badge-gray",
  DLQ: "badge-red",
  ACTIVE: "badge-green",
  OFFLINE: "badge-gray",
};

export default function StatusBadge({ status }: { status: string }) {
  const cls = COLORS[status] ?? "badge-gray";
  return <span className={`badge ${cls}`}>{status}</span>;
}
