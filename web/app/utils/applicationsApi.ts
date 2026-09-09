import { apiClient } from "./apiClient";

export type EnvironmentKey = "production" | "staging";

export interface ApplicationEnvironment {
  id: string;
  project_id: string;
  environment_key: EnvironmentKey;
  runtime_path: string | null;
  branch: string | null;
  domain: string | null;
  service_identifier: string | null;
  read_only_default: boolean;
}

export interface ApplicationInventoryItem {
  id: string;
  identity: string;
  display_name: string;
  source_path: string | null;
  classification: "managed_application" | "development_only" | "system_tool";
  environments: ApplicationEnvironment[];
}

export async function fetchApplications(token: string): Promise<ApplicationInventoryItem[]> {
  const response = await apiClient.fetch("http://localhost:8080/api/v1/applications", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error("Applications inventory request failed");
  return response.json() as Promise<ApplicationInventoryItem[]>;
}
