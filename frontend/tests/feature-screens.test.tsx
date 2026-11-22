import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ToastProvider } from "@/components/ui";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { HarborSession, SessionProvider } from "@/lib/session";
import { ThemeProvider } from "@/lib/theme";
import MenuPage from "@/app/menu/page";
import PrescriptionUploadPage from "@/app/members/[id]/prescription/page";
import PatientReminderPage from "@/app/patient/[token]/page";
import EngineExplorerPage from "@/app/engine/page";
import { harborApi } from "@/lib/api";

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "member-1", token: "pt-demo-token" }),
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/menu",
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
    [k: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    harborApi: {
      ...actual.harborApi,
      listMembers: vi.fn(),
      suggestMenu: vi.fn(),
      reviewMenu: vi.fn(),
      markMenuCooked: vi.fn(),
      getDrugClasses: vi.fn(),
      uploadPrescription: vi.fn(),
      confirmPrescription: vi.fn(),
      updateHouseholdSettings: vi.fn(),
      getPatientDueReminders: vi.fn(),
      markPatientDoseTaken: vi.fn(),
      getEngineCatalog: vi.fn(),
      checkEngineRuleTrace: vi.fn(),
    },
  };
});

function LanguageSwitchBar() {
  const { locale, toggleLocale } = useI18n();
  return (
    <button type="button" data-testid="test-locale-toggle" onClick={toggleLocale}>
      {locale}
    </button>
  );
}

function renderWithProviders(ui: React.ReactNode, session: HarborSession | null = null) {
  window.localStorage.setItem("harbor_theme", "light");
  window.localStorage.setItem("harbor_locale", "bn");
  if (session) {
    window.localStorage.setItem("harbor_session", JSON.stringify(session));
  } else {
    window.localStorage.removeItem("harbor_session");
  }
  return render(
    <ThemeProvider>
      <I18nProvider>
        <SessionProvider>
          <ToastProvider>
            <LanguageSwitchBar />
            {ui}
          </ToastProvider>
        </SessionProvider>
      </I18nProvider>
    </ThemeProvider>,
  );
}

const DEMO_SESSION: HarborSession = {
  householdId: "hh-1",
  householdName: "হোসেন পরিবার",
  accessCode: "DEMO26",
  token: "tok-123",
  consentGiven: true,
  mealTimes: { breakfast: "08:00", lunch: "13:30", dinner: "21:00" },
  monthlyBudgetBdt: 15000,
};

describe("Phase 4 Feature Screens", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        media: "",
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it("MenuPage triggers suggest, displays SAFE_WITH_SPLIT & score breakdown, and switches EN/BN", async () => {
    vi.mocked(harborApi.listMembers).mockResolvedValue({ members: [] });
    vi.mocked(harborApi.suggestMenu).mockResolvedValue({
      for_date: "2026-11-22",
      meal: "dinner",
      people_count: 4,
      present_member_names: ["বাবা", "মা", "আরিফ", "সুমাইয়া"],
      guest_count: 0,
      total_candidates: 8,
      validated: true,
      used_template: true,
      used_fallback: false,
      top_3: [
        {
          recipe_id: "r1",
          key: "lau_dal",
          name_bn: "লাউ ডাল",
          name_en: "Bottle Gourd Lentils",
          category: "dal",
          servings_base: 4,
          scaled_servings: 4,
          status: "SAFE_WITH_SPLIT",
          split_for: ["মা"],
          split_step_bn: "লবণ দেওয়ার আগে মায়ের অংশ আলাদা করুন",
          reasons: ["SAFE_WITH_SPLIT"],
          score: 0.91,
          components: { safety_score: 1.0, pantry_score: 0.85 },
          missing_ingredients: [],
          shortfall_cost_bdt: 0,
          explanation_bn: "সবাই লাউ ডাল নিরাপদে খেতে পারবেন।",
          explanation_en: "Everyone can safely enjoy Bottle Gourd Lentils.",
          split_instruction_bn: "লবণ দেওয়ার আগে মায়ের অংশ আলাদা করুন",
          split_instruction_en: "Set aside Mother's portion before adding salt.",
          rule_ids: ["PRESET_LOW_SODIUM"],
          used_template: true,
        },
      ],
      excluded: [
        {
          recipe_id: "r2",
          key: "chingri_bhuna",
          name_bn: "চিংড়ি ভুনা",
          name_en: "Prawn Curry",
          reasons: ["ALLERGY_MATCH"],
          member_details: [
            {
              member_name: "আরিফ",
              status: "BLOCKED",
              reasons: ["ALLERGY_MATCH"],
              trace: ["Blocked by prawn_shellfish allergy"],
            },
          ],
        },
      ],
    });

    renderWithProviders(<MenuPage />, DEMO_SESSION);

    fireEvent.click(screen.getByTestId("menu-suggest-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("menu-dish-card-0")).toBeInTheDocument();
    });

    expect(screen.getByTestId("menu-dish-card-0")).toHaveTextContent("লাউ ডাল");
    expect(screen.getByTestId("menu-split-callout-0")).toHaveTextContent("লবণ দেওয়ার আগে");

    fireEvent.click(screen.getByTestId("menu-score-toggle-0"));
    expect(screen.getByTestId("menu-score-panel-0")).toBeInTheDocument();

    // Expand excluded panel
    fireEvent.click(screen.getByText(/কেন বাদ পড়ল/));
    expect(screen.getByText(/চিংড়ি ভুনা/)).toBeInTheDocument();

    // Toggle full UI to English and verify localized dish title + explanation appear
    fireEvent.click(screen.getByTestId("test-locale-toggle"));
    expect(screen.getByTestId("menu-dish-card-0")).toHaveTextContent("Bottle Gourd Lentils");
    expect(screen.getByText(/Set aside Mother's portion before adding salt/)).toBeInTheDocument();
  });

  it("PrescriptionUploadPage enforces consent gate and shows zero dose inputs in draft table", async () => {
    vi.mocked(harborApi.getDrugClasses).mockResolvedValue({
      drug_classes: [
        { value: "ace_inhibitor", label_bn: "ACE ইনহিবিটর", label_en: "ACE Inhibitor" },
        { value: "none_modelled", label_bn: "মডেল করা নেই", label_en: "Not modelled" },
      ],
      note_bn: "note bn",
      note_en: "note en",
    });

    const { unmount } = renderWithProviders(<PrescriptionUploadPage />, {
      ...DEMO_SESSION,
      consentGiven: false,
    });
    expect(screen.getByTestId("rx-consent-gate")).toBeInTheDocument();
    expect(screen.queryByTestId("rx-file-input")).not.toBeInTheDocument();
    unmount();

    vi.mocked(harborApi.uploadPrescription).mockResolvedValue({
      prescription_id: "rx-1",
      member_id: "member-1",
      status: "draft",
      image_stored: false,
      confirmation_token: "ctok-1",
      medicines: [
        {
          name_as_written: "Enalapril",
          generic_guess: "enalapril",
          timing: "after_food",
          times_per_day: 2,
          confidence: 0.94,
          suggested_drug_class: "ace_inhibitor",
          drug_match_confidence: 1.0,
          low_confidence: false,
        },
      ],
      diet_notes: ["কম লবণ খান"],
      overall_confidence: 0.94,
      extraction_failed: false,
      scope_note_bn: "কোনো ডোজ সংরক্ষণ করা হয় না।",
      scope_note_en: "Doses are never saved.",
    });

    renderWithProviders(<PrescriptionUploadPage />, DEMO_SESSION);
    const fileInput = screen.getByTestId("rx-file-input") as HTMLInputElement;
    const dummyFile = new File(["img"], "rx.jpg", { type: "image/jpeg" });
    fireEvent.change(fileInput, { target: { files: [dummyFile] } });
    fireEvent.click(screen.getByTestId("rx-extract-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("rx-draft-table")).toBeInTheDocument();
    });

    expect(screen.getByDisplayValue("Enalapril")).toBeInTheDocument();
    expect(screen.getByTestId("rx-row-class-0")).toHaveValue("ace_inhibitor");
    expect(screen.queryByText(/5 mg|mg|মিগ্রা/i)).not.toBeInTheDocument();
  });

  it("PatientReminderPage hides disease/medicine names and calls markPatientDoseTaken on dome tap", async () => {
    vi.mocked(harborApi.getPatientDueReminders).mockResolvedValue({
      member_name: "মা",
      now: "2026-11-22T21:15:00+06:00",
      has_due_dose: true,
      due_doses: [
        {
          dose_id: "dose-1",
          due_at: "2026-11-22T21:15:00+06:00",
          window_end: "2026-11-22T22:15:00+06:00",
          status: "pending",
          prompt_bn: "ওষুধের সময় হয়েছে",
          prompt_en: "Time for medicine",
        },
      ],
      upcoming_doses: [],
      taken_today_count: 1,
    });
    vi.mocked(harborApi.markPatientDoseTaken).mockResolvedValue({
      dose_id: "dose-1",
      status: "taken",
      confirmed_at: "2026-11-22T21:16:00+06:00",
    });

    renderWithProviders(<PatientReminderPage />, null);

    await waitFor(() => {
      expect(screen.getByTestId("patient-due-heading")).toBeInTheDocument();
    });

    const containerText = screen.getByTestId("patient-screen").textContent || "";
    expect(containerText).toContain("ওষুধের সময় হয়েছে");
    expect(containerText).not.toMatch(/diabetes|hypertension|kidney|Enalapril|CKD/i);

    fireEvent.click(screen.getByTestId("patient-dome-button"));
    await waitFor(() => {
      expect(harborApi.markPatientDoseTaken).toHaveBeenCalledWith("dose-1", "pt-demo-token", "bn");
    });
  });

  it("EngineExplorerPage loads catalog and displays deterministic rule trace", async () => {
    vi.mocked(harborApi.getEngineCatalog).mockResolvedValue({
      recipes: [
        {
          id: "rec-1",
          key: "palong_shak",
          name_bn: "পালং শাক",
          name_en: "Spinach Fry",
          category: "bhaji",
          split_removes: [],
        },
      ],
      members: [],
      presets: ["low_potassium", "low_sodium"],
      allergens: ["prawn_shellfish"],
      drug_classes: ["ace_inhibitor", "none_modelled"],
      age_groups: ["adult", "elder"],
    });
    vi.mocked(harborApi.checkEngineRuleTrace).mockResolvedValue({
      member_name: "Test Profile",
      recipe_key: "palong_shak",
      recipe_name_bn: "পালং শাক",
      recipe_name_en: "Spinach Fry",
      status: "BLOCKED",
      reasons: ["DRUG_ACE_HIGH_POTASSIUM"],
      trace: ["Member has ace_inhibitor + spinach high potassium -> BLOCKED"],
      split_ingredients: [],
      ingredients: [
        {
          key: "spinach",
          name_bn: "পালং শাক",
          name_en: "Spinach",
          potassium_level: "high",
          purine_level: "medium",
          sodium_level: "low",
          gi_level: "low",
          allergen_tags: [],
        },
      ],
    });

    renderWithProviders(<EngineExplorerPage />, DEMO_SESSION);

    await waitFor(() => {
      expect(screen.getByTestId("engine-run-btn")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("engine-run-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("engine-result-card")).toBeInTheDocument();
    });

    expect(screen.getByTestId("engine-result-card")).toHaveTextContent(
      "Member has ace_inhibitor + spinach high potassium -> BLOCKED",
    );
    expect(screen.getByText(/DRUG_ACE_HIGH_POTASSIUM/)).toBeInTheDocument();
  });
});
