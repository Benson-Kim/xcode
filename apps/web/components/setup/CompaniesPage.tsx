"use client";

import { useState } from "react";

import { apiRequest, useStreamedList } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import {
  Banner,
  Button,
  DataTable,
  Field,
  FormActions,
  PageHeader,
  StatusBadge,
  Td,
  TextInput,
  Toolbar,
  Tr,
  useToast,
} from "../ui";
import type { Company } from "./shared";

// Whether the company carries an archive date, even one still ahead of the business date. Older rows had none, so inactive counts too.
const archivedOnRecord = (company: Company) =>
  Boolean(company.archivedOn) || company.active === false;

export function CompaniesPage() {
  const [name, setName] = useState("");
  const [addError, setAddError] = useState("");
  // Changes carry no typed reason: the server writes one for the change log.
  const [renaming, setRenaming] = useState<{
    id: string;
    name: string;
    error: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const companies = useStreamedList<Company>("setup/companies");
  const rows = companies.items;

  const toast = useToast();
  const { formatDateOnly } = useFormats();

  async function add() {
    const trimmed = name.trim();
    if (!trimmed) return setAddError("Enter the company name.");
    if (
      rows.some(
        (company) => company.name.toLowerCase() === trimmed.toLowerCase(),
      )
    )
      return setAddError("This company already exists.");
    setBusy(true);
    try {
      await apiRequest("setup/companies", {
        method: "POST",
        body: JSON.stringify({ name: trimmed }),
      });
      setName("");
      setAddError("");
      toast(`${trimmed} added.`);
      companies.reload();
    } catch (value) {
      setAddError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveRename(company: Company) {
    if (!renaming) return;
    const trimmed = renaming.name.trim();
    if (!trimmed)
      return setRenaming({ ...renaming, error: "Enter the new name." });
    if (
      rows.some(
        (other) =>
          other.id !== company.id &&
          other.name.toLowerCase() === trimmed.toLowerCase(),
      )
    )
      return setRenaming({
        ...renaming,
        error: "Another company already has this name.",
      });
    if (trimmed === company.name) return setRenaming(null);
    setBusy(true);
    try {
      await apiRequest(`setup/companies/${company.id}`, {
        method: "PUT",
        body: JSON.stringify({ name: trimmed }),
      });
      setRenaming(null);
      toast(`Company renamed to ${trimmed}.`);
      companies.reload();
    } catch (value) {
      setRenaming({ ...renaming, error: (value as Error).message });
    } finally {
      setBusy(false);
    }
  }

  // The stored archive date decides, not `active`: that follows the business date, so an archive dated ahead of it is cancelled by restoring.
  async function setArchived(company: Company, archived: boolean) {
    setBusy(true);
    try {
      await apiRequest(
        `setup/companies/${company.id}/${archived ? "archive" : "restore"}`,
        {
          method: "POST",
          body: "{}",
        },
      );
      toast(
        archived ? `${company.name} archived.` : `${company.name} restored.`,
      );
      companies.reload();
    } catch (value) {
      setAddError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <PageHeader
        title="PSV companies"
        description="Every vehicle belongs to one company. Archive a company after its vehicles have left the fleet."
      />
      {(companies.error || addError) && (
        <Banner className="mt-5">{companies.error || addError}</Banner>
      )}
      <Toolbar align="start">
        <Field
          id="new-company"
          label="New PSV company"
          error={addError}
          className="min-w-55 flex-1"
        >
          <TextInput
            placeholder="Company name"
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              setAddError("");
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") void add();
            }}
          />
        </Field>
        <Button
          tone="ok"
          className="mt-6.5 max-[480px]:mt-0"
          disabled={busy}
          onClick={() => void add()}
        >
          Add company
        </Button>
      </Toolbar>
      <DataTable
        columns={[
          { label: "Company" },
          { label: "Status" },
          { label: "Vehicles", numeric: true },
          { label: "Actions", hidden: true },
        ]}
        loading={companies.loading}
        pendingRows={companies.pendingRows}
        loadingLabel="Loading companies"
        isEmpty={!rows.length}
        failed={Boolean(companies.error)}
        emptyMessage="No PSV companies yet. Add the first one above."
      >
        {rows.map((company) =>
          renaming?.id === company.id ? (
            <Tr key={company.id}>
              <Td colSpan={4}>
                <div className="flex flex-wrap items-start gap-3">
                  <Field
                    id={`rename-${company.id}`}
                    label="New name"
                    error={renaming.error}
                    className="min-w-50 flex-1"
                  >
                    <TextInput
                      autoFocus
                      value={renaming.name}
                      onChange={(event) =>
                        setRenaming({
                          ...renaming,
                          name: event.target.value,
                          error: "",
                        })
                      }
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void saveRename(company);
                        if (event.key === "Escape") setRenaming(null);
                      }}
                    />
                  </Field>
                  <Button
                    tone="ok"
                    className="mt-6.5"
                    disabled={busy}
                    onClick={() => void saveRename(company)}
                  >
                    Save
                  </Button>
                  <Button
                    className="mt-6.5"
                    tone="quiet"
                    onClick={() => setRenaming(null)}
                  >
                    Cancel
                  </Button>
                </div>
              </Td>
            </Tr>
          ) : (
            <Tr key={company.id}>
              <Td label="Company">
                <strong>{company.name}</strong>
              </Td>
              <Td label="Status">
                <StatusBadge
                  tone={
                    company.active === false
                      ? "off"
                      : company.archivedOn
                        ? "warn"
                        : "ok"
                  }
                >
                  {company.active === false
                    ? "Archived"
                    : company.archivedOn
                      ? `Archives on ${formatDateOnly(company.archivedOn)}`
                      : "Active"}
                </StatusBadge>
              </Td>
              <Td label="Vehicles" numeric>
                {company.vehicleCount}
              </Td>
              <Td>
                {/* Every row ends with its actions, side by side at the end of the row (.row-acts). */}
                <FormActions className="justify-end gap-2">
                  {company.active !== false && (
                    <Button
                      tone="outline"
                      disabled={busy}
                      onClick={() =>
                        setRenaming({
                          id: company.id,
                          name: company.name,
                          error: "",
                        })
                      }
                      aria-label={`Rename ${company.name}`}
                    >
                      Rename
                    </Button>
                  )}
                  {/* An archive dated ahead has not taken effect, so it can still be cancelled with Restore. */}
                  <Button
                    tone={archivedOnRecord(company) ? "ok" : "warn"}
                    disabled={busy}
                    aria-label={`${archivedOnRecord(company) ? "Restore" : "Archive"} ${company.name}`}
                    onClick={() =>
                      void setArchived(company, !archivedOnRecord(company))
                    }
                  >
                    {archivedOnRecord(company) ? "Restore" : "Archive"}
                  </Button>
                </FormActions>
              </Td>
            </Tr>
          ),
        )}
      </DataTable>
    </section>
  );
}
