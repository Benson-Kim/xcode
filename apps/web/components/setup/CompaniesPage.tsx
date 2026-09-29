"use client";

import { useState } from "react";
import { apiRequest } from "../../lib/data";
import { useStreamedList } from "../../lib/data";
import { Banner, Button, DataTable, Field, PageHeader, RowButton, TextInput, Toolbar, Td, Tr, useToast } from "../ui";
import type { Company } from "./shared";

export function CompaniesPage() {
  const companies = useStreamedList<Company>("setup/companies");
  const toast = useToast();
  const [name, setName] = useState("");
  const [addError, setAddError] = useState("");
  // Changes carry no typed reason: the server writes one for the change log.
  const [renaming, setRenaming] = useState<{ id: string; name: string; error: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const rows = companies.items;

  async function add() {
    const trimmed = name.trim();
    if (!trimmed) return setAddError("Enter the company name.");
    if (rows.some((company) => company.name.toLowerCase() === trimmed.toLowerCase())) return setAddError("This company already exists.");
    setBusy(true);
    try {
      await apiRequest("setup/companies", { method: "POST", body: JSON.stringify({ name: trimmed }) });
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
    if (!trimmed) return setRenaming({ ...renaming, error: "Enter the new name." });
    if (rows.some((other) => other.id !== company.id && other.name.toLowerCase() === trimmed.toLowerCase()))
      return setRenaming({ ...renaming, error: "Another company already has this name." });
    if (trimmed === company.name) return setRenaming(null);
    setBusy(true);
    try {
      await apiRequest(`setup/companies/${company.id}`, { method: "PUT", body: JSON.stringify({ name: trimmed }) });
      setRenaming(null);
      toast(`Company renamed to ${trimmed}.`);
      companies.reload();
    } catch (value) {
      setRenaming({ ...renaming, error: (value as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function setArchived(company: Company, archived: boolean) {
    setBusy(true);
    try {
      await apiRequest(`setup/companies/${company.id}/${archived ? "archive" : "restore"}`, {
        method: "POST",
        body: "{}",
      });
      toast(archived ? `${company.name} archived.` : `${company.name} restored.`);
      companies.reload();
    } catch (value) {
      setAddError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <PageHeader title="PSV companies" description="Every vehicle belongs to one company. Archive a company after its vehicles have left the fleet." />
      {(companies.error || addError) && <Banner className="mt-5">{companies.error || addError}</Banner>}
      <Toolbar align="start">
        <Field id="new-company" label="New PSV company" error={addError} className="min-w-55 flex-1">
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
        <Button className="mt-6.5" disabled={busy} onClick={() => void add()}>
          Add company
        </Button>
      </Toolbar>
      <DataTable
        columns={[{ label: "Company" }, { label: "Status" }, { label: "Vehicles", numeric: true }, { label: "Actions", hidden: true }]}
        loading={companies.loading}
        pendingRows={companies.pendingRows}
        loadingLabel="Loading companies"
        isEmpty={!rows.length}
        emptyMessage="No PSV companies yet. Add the first one above."
      >
        {rows.map((company) =>
          renaming?.id === company.id ? (
            <Tr key={company.id}>
              <Td colSpan={4}>
                <div className="flex flex-wrap items-start gap-3">
                  <Field id={`rename-${company.id}`} label="New name" error={renaming.error} className="min-w-50 flex-1">
                    <TextInput
                      autoFocus
                      value={renaming.name}
                      onChange={(event) => setRenaming({ ...renaming, name: event.target.value, error: "" })}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void saveRename(company);
                        if (event.key === "Escape") setRenaming(null);
                      }}
                    />
                  </Field>
                  <Button className="mt-6.5" disabled={busy} onClick={() => void saveRename(company)}>
                    Save
                  </Button>
                  <Button className="mt-6.5" tone="outline" onClick={() => setRenaming(null)}>
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
              <Td label="Status">{company.active === false ? "Archived" : "Active"}</Td>
              <Td label="Vehicles" numeric>{company.vehicleCount}</Td>
              <Td>
                {company.active !== false && (
                  <RowButton onClick={() => setRenaming({ id: company.id, name: company.name, error: "" })} aria-label={`Rename ${company.name}`}>
                    Rename
                  </RowButton>
                )}
                <Button
                  tone="outline"
                  disabled={busy}
                  aria-label={`${company.active !== false ? "Archive" : "Restore"} ${company.name}`}
                  onClick={() => void setArchived(company, company.active !== false)}
                >
                  {company.active !== false ? "Archive" : "Restore"}
                </Button>
              </Td>
            </Tr>
          ),
        )}
      </DataTable>
    </section>
  );
}
