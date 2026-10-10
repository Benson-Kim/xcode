"use client";

import { useState } from "react";

import { apiRequest, streamError } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import {
  Banner,
  Button,
  DataTable,
  Dialog,
  Field,
  PageHeader,
  ListPager,
  RowAction,
  StatusBadge,
  Td,
  TextInput,
  Tr,
  useToast,
} from "../ui";
import { usePagedList } from "../usePagedList";
import type { Company } from "./shared";

// Whether the company carries an archive date, even one still ahead of the business date. Older rows had none, so inactive counts too.
const archivedOnRecord = (company: Company) =>
  Boolean(company.archivedOn) || company.active === false;

export function CompaniesPage() {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [addError, setAddError] = useState("");
  // Changes carry no typed reason: the server writes one for the change log.
  const [renaming, setRenaming] = useState<{
    id: string;
    name: string;
    error: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const companies = usePagedList<Company>("setup/companies");
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
      setAdding(false);
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

  function closeAdd() {
    setAdding(false);
    setName("");
    setAddError("");
  }

  const renamingCompany = renaming
    ? rows.find((company) => company.id === renaming.id)
    : undefined;

  return (
    <section>
      <PageHeader
        title="PSV companies"
        description="Every vehicle belongs to one company. Archive a company after its vehicles have left the fleet."
        actions={
          <Button tone="primary" onClick={() => setAdding(true)}>
            New company
          </Button>
        }
      />
      {(companies.error || (addError && !adding)) && (
        <Banner className="mb-3.5">{streamError(companies) || addError}</Banner>
      )}
      <Dialog
        open={adding}
        title="New company"
        size="md"
        onClose={closeAdd}
        footer={
          <>
            <Button tone="outline" onClick={closeAdd}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="company-add-form"
              tone="ok"
              disabled={busy}
            >
              Add company
            </Button>
          </>
        }
      >
        <form
          id="company-add-form"
          onSubmit={(event) => {
            event.preventDefault();
            void add();
          }}
        >
          <Field
            id="new-company"
            label="New PSV company"
            error={adding ? addError : ""}
          >
            <TextInput
              placeholder="Company name"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                setAddError("");
              }}
            />
          </Field>
        </form>
      </Dialog>
      <Dialog
        open={Boolean(renaming && renamingCompany)}
        title="Rename company"
        subtitle={renamingCompany?.name}
        size="md"
        onClose={() => setRenaming(null)}
        footer={
          <>
            <Button tone="outline" onClick={() => setRenaming(null)}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="company-rename-form"
              tone="ok"
              disabled={busy}
            >
              Save
            </Button>
          </>
        }
      >
        {renaming && renamingCompany && (
          <form
            id="company-rename-form"
            onSubmit={(event) => {
              event.preventDefault();
              void saveRename(renamingCompany);
            }}
          >
            <Field
              id={`rename-${renamingCompany.id}`}
              label="New name"
              error={renaming.error}
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
              />
            </Field>
          </form>
        )}
      </Dialog>
      <DataTable
        columns={[
          { label: "Company" },
          { label: "Status" },
          { label: "Vehicles", numeric: true },
          { label: "Actions", hidden: true },
        ]}
        loading={companies.loading}
        loadingLabel="Loading companies"
        isEmpty={!rows.length}
        failed={Boolean(companies.error)}
        emptyMessage="No PSV companies yet. Add the first one above."
      >
        {rows.map((company) => (
          <Tr key={company.id}>
            <Td label="Company">
              <span className="font-semibold text-ink">{company.name}</span>
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
              <div className="flex items-center justify-end gap-0.5 whitespace-nowrap">
                {company.active !== false && (
                  <RowAction
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
                  </RowAction>
                )}
                {/* An archive dated ahead has not taken effect, so it can still be cancelled with Restore. */}
                <RowAction
                  tone={archivedOnRecord(company) ? "ok" : "warn"}
                  disabled={busy}
                  aria-label={`${archivedOnRecord(company) ? "Restore" : "Archive"} ${company.name}`}
                  onClick={() =>
                    void setArchived(company, !archivedOnRecord(company))
                  }
                >
                  {archivedOnRecord(company) ? "Restore" : "Archive"}
                </RowAction>
              </div>
            </Td>
          </Tr>
        ))}
      </DataTable>
      <ListPager list={companies} />
    </section>
  );
}
