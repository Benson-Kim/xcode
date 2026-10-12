"use client";

import { Fragment } from "react";

import { weekdayIndex, weekdayName } from "@xcode/shared/dates";

import { useResource } from "../../lib/data";
import { recurringPath } from "../../lib/endpoints/recurring";
import { useFormats } from "../../lib/formats";
import { recurringFrequency } from "../recurringPresentation";
import { Banner, Button, Dialog, FormSkeleton, RegPlate } from "../ui";
import type { RecurringItem, RecurringRuns } from "./shared";

// The last ten run dates of one saving: each vehicle it saved for and how much.
export function RecurringRunsDialog({
  item,
  onClose,
}: {
  item: RecurringItem;
  onClose: () => void;
}) {
  const { formatDateOnly, formatNumber, kes } = useFormats();
  const runs = useResource<RecurringRuns>(`${recurringPath(item.id)}/runs`);
  const data = runs.data;
  return (
    <Dialog
      open
      size="md"
      title={item.name}
      subtitle={`${recurringFrequency(item)}.`}
      onClose={onClose}
      footer={<Button onClick={onClose}>Close</Button>}
    >
      {runs.error ? (
        <Banner>{runs.error}</Banner>
      ) : !data ? (
        <FormSkeleton cards={1} fields={3} label="Loading the runs" />
      ) : (
        <>
          <div className="msum">
            <div>
              <span>Runs</span>
              <b>{formatNumber(data.runCount)}</b>
            </div>
            <div className="t">
              <span>Balance</span>
              <b>{kes(data.total)}</b>
            </div>
          </div>
          <div className="tbl">
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Vehicle</th>
                    <th scope="col">Outcome</th>
                    <th scope="col" className="r">
                      Saved
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.runs.length === 0 && (
                    <tr>
                      <td colSpan={3} className="empty">
                        No runs yet.
                      </td>
                    </tr>
                  )}
                  {data.runs.map((run) => (
                    <Fragment key={run.date}>
                      <tr className="grp" data-day={run.date}>
                        <td colSpan={3}>
                          <div>
                            <span>
                              {weekdayName(weekdayIndex(run.date))}{" "}
                              {formatDateOnly(run.date)}
                            </span>
                            <span>{run.shares.length} saved</span>
                          </div>
                        </td>
                      </tr>
                      {run.shares.map((share) => (
                        <tr key={share.vehicleId}>
                          <td>
                            <RegPlate>{share.registration}</RegPlate>
                          </td>
                          <td>
                            <span className="chip ok">Saved</span>
                          </td>
                          <td className="r tot">
                            {formatNumber(share.amount)}
                          </td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </Dialog>
  );
}
