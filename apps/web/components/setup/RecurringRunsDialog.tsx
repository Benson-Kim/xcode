"use client";

import { Fragment } from "react";

import { weekdayIndex, weekdayName } from "@xcode/shared/dates";

import { useResource } from "../../lib/data";
import { recurringPath } from "../../lib/endpoints/recurring";
import { useFormats } from "../../lib/formats";
import { recurringFrequency } from "../recurringPresentation";
import { Banner, Button, Dialog, FormSkeleton, RegPlate } from "../ui";
import { ruleText, runTally } from "./RecurringRows";
import type { RecurringItem, RecurringRuns, RunState } from "./shared";

const tally = (shares: { state?: RunState }[]) => {
  const counts = { saved: 0, skipped: 0, held: 0 };
  for (const share of shares) counts[share.state ?? "saved"]++;
  return runTally(counts);
};

// The runs of one saving: each vehicle, the revenue measured, and what happened. The last ten run dates.
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
  const opening = item.opening?.total ?? 0;
  const balance = item.balance ?? data?.total ?? 0;
  return (
    <Dialog
      open
      size="md"
      title={item.name}
      subtitle={`${recurringFrequency(item)}. ${ruleText(item, kes)}.`}
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
              <span>
                Opening balance
                {item.opening ? `, ${formatDateOnly(item.opening.date)}` : ""}
              </span>
              <b>{formatNumber(opening)}</b>
            </div>
            <i>+</i>
            <div>
              <span>Saved since</span>
              <b>{formatNumber(balance - opening)}</b>
            </div>
            <i>=</i>
            <div className="t">
              <span>Balance</span>
              <b>{formatNumber(balance)}</b>
            </div>
          </div>
          <div className="tbl">
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Vehicle</th>
                    <th scope="col" className="r">
                      Revenue
                    </th>
                    <th scope="col">Outcome</th>
                    <th scope="col" className="r">
                      Saved
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.runs.length === 0 && (
                    <tr>
                      <td colSpan={4} className="empty">
                        No runs yet.
                      </td>
                    </tr>
                  )}
                  {data.runs.map((run) => (
                    <Fragment key={run.date}>
                      <tr className="grp" data-day={run.date}>
                        <td colSpan={4}>
                          <div>
                            <span>
                              {weekdayName(weekdayIndex(run.date))}{" "}
                              {formatDateOnly(run.date)}
                            </span>
                            <span>{tally(run.shares)}</span>
                          </div>
                        </td>
                      </tr>
                      {run.shares.map((share) => {
                        const state = share.state ?? "saved";
                        return (
                          <tr key={share.vehicleId}>
                            <td>
                              <RegPlate>{share.registration}</RegPlate>
                            </td>
                            <td className="r">
                              {item.condition &&
                              share.revenue !== undefined &&
                              share.revenue !== null
                                ? `${formatNumber(share.revenue)}${state === "held" ? " so far" : ""}`
                                : ""}
                            </td>
                            <td>
                              {state === "saved" ? (
                                <span className="chip ok">Saved</span>
                              ) : state === "skipped" ? (
                                <span className="chip mute">
                                  Skipped, below{" "}
                                  {formatNumber(item.condition?.min ?? 0)}
                                </span>
                              ) : (
                                <span className="chip wait">
                                  Waiting for revenue
                                </span>
                              )}
                            </td>
                            <td className="r tot">
                              {state === "saved"
                                ? formatNumber(share.amount)
                                : ""}
                            </td>
                          </tr>
                        );
                      })}
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
