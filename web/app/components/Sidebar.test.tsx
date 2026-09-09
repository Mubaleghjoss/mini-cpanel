import { render, screen } from "@testing-library/react";
import Sidebar from "./Sidebar";

const props = {
  activeTab: "dashboard" as const,
  setActiveTab: jest.fn(),
  agentStatus: "online" as const,
  onViewLogs: jest.fn(),
  onLogout: jest.fn(),
  isOpen: false,
  onClose: jest.fn(),
};

describe("Sidebar application navigation", () => {
  it.each(["viewer", "developer", "super_admin"])(
    "shows Applications for the %s role",
    (userRole) => {
      render(<Sidebar {...props} userRole={userRole} />);
      expect(screen.getByTestId("tab-applications")).toHaveTextContent("Applications");
    },
  );
});
