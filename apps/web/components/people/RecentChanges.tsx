import { useFormats } from "../../lib/formats";
import type { ChangeLogPage } from "../../lib/types";
import type { HistoryRow } from "../setup/shared";
import {
  Card,
  CardHeader,
  CardList,
  CardListItem,
  Hint,
  ListSkeleton,
} from "../ui";

type Props = {
  loading: boolean;
  data?: ChangeLogPage<HistoryRow>;
  error: string;
};

export function RecentChanges({ loading, data, error }: Props) {
  const { formatDateTime } = useFormats();
  return (
    <Card className="mt-4">
      <CardHeader
        title="Recent changes"
        description="The latest setup changes. Every change is in the change log."
      />
      {loading ? (
        <div role="status" aria-busy="true">
          <span className="sr-only">Loading recent changes</span>
          <ListSkeleton rows={3} />
        </div>
      ) : data?.items.length ? (
        <CardList>
          {data.items.map((row) => (
            <CardListItem
              key={row.version}
              left={row.reason}
              leftSub={row.actorName}
              rightSub={formatDateTime(row.occurredAt)}
            />
          ))}
        </CardList>
      ) : (
        <Hint>{error || "No changes yet."}</Hint>
      )}
    </Card>
  );
}
