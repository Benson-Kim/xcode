import { apiRequest } from "../data";

export const EXPENSE_CATEGORIES_PATH = "setup/expense-categories";
export const EXPENSE_MAIN_CATEGORIES_PATH = "setup/expense-main-categories";

export type CategoryRequest = { name: string; mainCategoryId: string | null };

const send = <T>(path: string, method: string, body?: object) =>
  apiRequest<T>(path, {
    method,
    ...(body ? { body: JSON.stringify(body) } : {}),
  });

export const catalogApi = {
  createMain: (name: string) =>
    send<{ id: string }>(EXPENSE_MAIN_CATEGORIES_PATH, "POST", { name }),
  renameMain: (id: string, name: string) =>
    send<{ id: string }>(`${EXPENSE_MAIN_CATEGORIES_PATH}/${id}`, "PUT", {
      name,
    }),
  createCategory: (body: CategoryRequest) =>
    send<{ id: string }>(EXPENSE_CATEGORIES_PATH, "POST", body),
  updateCategory: (id: string, body: CategoryRequest) =>
    send<{ id: string }>(`${EXPENSE_CATEGORIES_PATH}/${id}`, "PUT", body),
  createItem: (categoryId: string, name: string) =>
    send<{ id: string }>(
      `${EXPENSE_CATEGORIES_PATH}/${categoryId}/items`,
      "POST",
      {
        name,
      },
    ),
  updateItem: (id: string, body: { name: string; categoryId?: string }) =>
    send<{ id: string }>(`setup/expense-items/${id}`, "PUT", body),
  setItemStopped: (id: string, stopped: boolean) =>
    send<{ id: string }>(
      `setup/expense-items/${id}/${stopped ? "stop" : "restore"}`,
      "POST",
      {},
    ),
};
