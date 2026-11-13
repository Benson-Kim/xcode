"use client";

import { useState } from "react";

import { apiRequest, streamError } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import { useSession } from "../../lib/session-context";
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
import { AddCompanyDialog } from "./AddCompanyDialog";
import { useDeleteRecord } from "./DeleteRecordDialog";
import type { Company } from "./shared";

// Whether the company carries an archive date, even one still ahead of the business date. Older rows had none, so inactive counts too.
const archivedOnRecord = (company: Company) =>
  Boolean(company.archivedOn) || company.active === false;

export function CompaniesPage() {
  const [adding, setAdding] = useState(false);
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
  const { can } = useSession();
  const canDelete = can("companies.manage") || can("companies.edit");
  const deletion = useDeleteRecord(companies.reload);

  const toast = useToast();
  const { formatDateOnly } = useFormats();

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

  const renamingCompany = renaming
    ? rows.find((company) => company.id === renaming.id)
    : undefined;

  return (
    <>
      <PageHeader
        title="PSV companies"
        actions={
          <Button tone="primary" onClick={() => setAdding(true)}>
            New company
          </Button>
        }
      />
      {(companies.error || (addError && !adding)) && (
        <Banner>{streamError(companies) || addError}</Banner>
      )}
      <DataTable
        columns={[
          { label: "PSV company" },
          { label: "Vehicles", numeric: true },
          { label: "Status" },
          { label: "Actions", numeric: true },
        ]}
        loading={companies.loading}
        loadingLabel="Loading companies"
        isEmpty={!rows.length}
        failed={Boolean(companies.error)}
        emptyMessage="No PSV companies yet. Add the first one above."
      >
        {rows.map((company) => (
          <Tr key={company.id}>
            <Td label="PSV company" className="item">
              {company.name}
            </Td>
            <Td label="Vehicles" numeric>
              {company.vehicleCount}
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
            <Td numeric>
              <CompanyActions
                company={company}
                busy={busy}
                canDelete={canDelete}
                onEdit={() =>
                  setRenaming({ id: company.id, name: company.name, error: "" })
                }
                onArchive={(archived) => void setArchived(company, archived)}
                onDelete={() =>
                  deletion.ask({
                    noun: "company",
                    name: company.name,
                    remove: () =>
                      apiRequest(`setup/companies/${company.id}`, {
                        method: "DELETE",
                      }),
                  })
                }
              />
            </Td>
          </Tr>
        ))}
      </DataTable>
      {adding && (
        <AddCompanyDialog
          taken={rows.map((company) => company.name)}
          onAdded={() => {
            setAdding(false);
            companies.reload();
          }}
          onClose={() => setAdding(false)}
        />
      )}
      <Dialog
        open={Boolean(renaming && renamingCompany)}
        title="Edit company"
        subtitle={renamingCompany?.name}
        size="sm"
        busy={busy}
        onClose={() => setRenaming(null)}
        footer={
          <>
            <Button
              tone="outline"
              disabled={busy}
              onClick={() => setRenaming(null)}
            >
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
            className="contents"
            onSubmit={(event) => {
              event.preventDefault();
              void saveRename(renamingCompany);
            }}
          >
            <Field
              id={`rename-${renamingCompany.id}`}
              label="Name"
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
      <ListPager list={companies} />
      {deletion.dialog}
    </>
  );
}

// A row's actions: edit, archive or restore, and delete for a company added by mistake (the server refuses one in
// use).
function CompanyActions({
  company,
  busy,
  canDelete,
  onEdit,
  onArchive,
  onDelete,
}: {
  company: Company;
  busy: boolean;
  canDelete: boolean;
  onEdit: () => void;
  onArchive: (archived: boolean) => void;
  onDelete: () => void;
}) {
  const archived = archivedOnRecord(company);
  return (
    <div className="tacts">
      {company.active !== false && (
        <RowAction
          disabled={busy}
          onClick={onEdit}
          aria-label={`Edit ${company.name}`}
        >
          Edit
        </RowAction>
      )}
      {/* An archive dated ahead has not taken effect, so it can still be cancelled with Restore. */}
      <RowAction
        tone={archived ? "ok" : "warn"}
        disabled={busy}
        aria-label={`${archived ? "Restore" : "Archive"} ${company.name}`}
        onClick={() => onArchive(!archived)}
      >
        {archived ? "Restore" : "Archive"}
      </RowAction>
      {canDelete && (
        <RowAction
          tone="bad"
          disabled={busy}
          aria-label={`Delete ${company.name}`}
          onClick={onDelete}
        >
          Delete
        </RowAction>
      )}
    </div>
  );
}
