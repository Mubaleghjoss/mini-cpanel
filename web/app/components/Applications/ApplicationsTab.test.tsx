import { render, screen, waitFor } from "@testing-library/react";
import ApplicationsTab from "./ApplicationsTab";
import { apiClient } from "@/app/utils/apiClient";

jest.mock("@/app/utils/apiClient", () => ({
  apiClient: { fetch: jest.fn() },
}));

const inventory = [
  {
    id: "pk-generus",
    identity: "pkgenerus",
    display_name: "PKGenerus",
    source_path: "/home/hermesadmin/projects/pembinaan-karakter-generus",
    classification: "managed_application",
    environments: [
      {
        id: "prod",
        project_id: "pk-generus",
        environment_key: "production",
        domain: "pkgenerus.my.id",
        branch: "main",
        runtime_path: "/var/www/pkgenerus.my.id",
        service_identifier: null,
        read_only_default: true,
      },
      {
        id: "stage",
        project_id: "pk-generus",
        environment_key: "staging",
        domain: "staging.pkgenerus.my.id",
        branch: "develop",
        runtime_path: "/var/www/pkgenerus-staging",
        service_identifier: null,
        read_only_default: false,
      },
    ],
  },
  {
    id: "sma-afbs",
    identity: "sma-afbs",
    display_name: "SMA AFBS",
    source_path: null,
    classification: "managed_application",
    environments: [],
  },
];

describe("ApplicationsTab", () => {
  beforeEach(() => {
    jest.mocked(apiClient.fetch).mockResolvedValue({
      ok: true,
      json: async () => inventory,
    } as Response);
  });

  it("renders the exact production warning and safe environment inventory", async () => {
    render(<ApplicationsTab token="token" />);

    expect(await screen.findByRole("heading", { name: "PKGenerus" })).toBeInTheDocument();
    expect(screen.getByText("PRODUCTION — READ ONLY")).toBeInTheDocument();
    expect(screen.getByText("/home/hermesadmin/projects/pembinaan-karakter-generus")).toBeInTheDocument();
    expect(screen.getByText("pkgenerus.my.id")).toBeInTheDocument();
    expect(screen.getByText("main")).toBeInTheDocument();
    expect(screen.getByText("/var/www/pkgenerus.my.id")).toBeInTheDocument();
    expect(screen.getByText("STAGING")).toBeInTheDocument();
    expect(screen.getByText("staging.pkgenerus.my.id")).toBeInTheDocument();
    expect(screen.getByText("develop")).toBeInTheDocument();
    expect(screen.getByText("/var/www/pkgenerus-staging")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "SMA AFBS" })).toBeInTheDocument();
    expect(screen.getByText("Source not recorded")).toBeInTheDocument();
    expect(screen.getByText("No environments recorded")).toBeInTheDocument();

    await waitFor(() => expect(apiClient.fetch).toHaveBeenCalledWith(
      "http://localhost:8080/api/v1/applications",
      { headers: { Authorization: "Bearer token" } },
    ));
  });
});
