import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import DatabasesTab from "./DatabasesTab";

const fetchMock = jest.fn();

jest.mock("@/app/utils/apiClient", () => ({
  apiClient: { fetch: (...args: unknown[]) => fetchMock(...args) },
}));

jest.mock("@/app/context/NotificationContext", () => ({
  useNotification: () => ({ showToast: jest.fn(), confirm: jest.fn() }),
}));

describe("DatabasesTab", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ tables: [] }) });
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: "primary-sqlite",
          name: "Primary Mini cPanel SQLite (minicpanel.db)",
          db_type: "sqlite",
        },
      ],
    });
  });

  it("keeps database browsing available without a raw SQL query entry point", async () => {
    render(<DatabasesTab token="test-token" addLog={jest.fn()} />);

    expect(screen.getByText("Active Databases")).toBeInTheDocument();
    expect(screen.queryByText("SQL QUERY EDITOR")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run query/i })).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/select \* from users/i)).not.toBeInTheDocument();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls.flat().join(" ")).not.toContain("/query");
  });

  it("continues to browse table rows through the safe data endpoint", async () => {
    fetchMock.mockReset();
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            id: "primary-sqlite",
            name: "Primary Mini cPanel SQLite (minicpanel.db)",
            db_type: "sqlite",
          },
        ],
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tables: ["users"] }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ columns: ["id"], rows: [[1]], total: 1 }),
      });

    render(<DatabasesTab token="test-token" addLog={jest.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "users" }));
    expect(await screen.findByText("Browse Data")).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock.mock.calls.flat().join(" ")).toContain("/tables/users/data?page=1&limit=20")
    );
    expect(fetchMock.mock.calls.flat().join(" ")).not.toContain("/query");
  });
});
