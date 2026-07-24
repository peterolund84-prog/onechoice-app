import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { HomePage } from "../pages/HomePage";
import { ResultPage } from "../pages/ResultPage";
import { ExecutePage } from "../pages/ExecutePage";
import { ListaPage } from "../pages/ListaPage";
import { AuthPage } from "../pages/AuthPage";
import { ClothesPage } from "../pages/ClothesPage";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { clearAuth } from "../lib/auth";
import type { Decision } from "../lib/types";

const decideFood: Decision = {
  ok: true,
  domain: "food",
  suggestion: "Pasta",
  justification: "Snabb och god.",
  decision_id: 42,
  id: 42,
  reroll_index: 0,
  locked: false,
  allows_shopping: true,
  context: {
    meal_type: "middag",
    shopping: { to_buy: { torrvaror: ["pasta"] } },
    recipe: {
      steps: ["Koka pasta."],
      ingredient_lines: ["pasta — 100 g"],
      kcal_per_portion: 400,
      protein_g_per_portion: 15,
      fat_g_per_portion: 10,
      carbs_g_per_portion: 60,
    },
  },
  image_url: "/v1/media/dish?title=Pasta",
};

vi.mock("../lib/api", () => {
  return {
    api: {
      base: "",
      home: vi.fn(async () => ({
        headline: "Middag?",
        sub: "Ett tryck — jag tar beslutet.",
        cta: "Bestäm åt mig",
        section_label: "Eller välj själv",
        something_else: "Något annat?",
        meal_type: "middag",
        domains: [
          { id: "food", label: "Mat" },
          { id: "clothes", label: "Kläder" },
          { id: "movie", label: "Film" },
          { id: "workout", label: "Träning" },
          { id: "weekend", label: "Helg" },
          { id: "fridge", label: "Fota kylen" },
        ],
      })),
      decide: vi.fn(async () => decideFood),
      acceptDecision: vi.fn(async () => ({
        ok: true,
        accepted: true,
        decision: { ...decideFood, accepted: true },
      })),
      listShopping: vi.fn(async () => ({
        items: [
          {
            id: 1,
            name: "mjölk",
            checked: false,
            category: "mejeri",
            user_id: "guest-x",
          },
        ],
      })),
      addShopping: vi.fn(async (name: string) => ({
        item: {
          id: 2,
          name,
          checked: false,
          category: "övrigt",
          user_id: "guest-x",
        },
      })),
      toggleShopping: vi.fn(async () => ({
        item: {
          id: 1,
          name: "mjölk",
          checked: true,
          category: "mejeri",
          user_id: "guest-x",
        },
      })),
      clearCheckedShopping: vi.fn(async () => ({ deleted: 1 })),
      authStatus: vi.fn(async () => ({ configured: false })),
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(async () => ({ ok: true })),
      me: vi.fn(),
      listDecisions: vi.fn(async () => ({ items: [] })),
      setFavorite: vi.fn(),
      mergeShopping: vi.fn(),
      shoppingShareText: vi.fn(async () => "lista"),
      domainMeta: vi.fn(),
      executeFood: vi.fn(async () => ({
        ok: true,
        recipe: decideFood.context?.recipe,
        shopping: decideFood.context?.shopping,
      })),
    },
  };
});

describe("Home", () => {
  beforeEach(() => {
    clearAuth();
    localStorage.clear();
    sessionStorage.clear();
  });

  it("renders and navigates to clothes domain", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/klader" element={<ClothesPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: /Middag/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Bestäm åt mig/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Film$/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Kläder$/i }));
    expect(await screen.findByText(/Vart ska du/i)).toBeInTheDocument();
  });

  it("decide → result → accept → execute", async () => {
    const user = userEvent.setup();
    const { api } = await import("../lib/api");
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/resultat" element={<ResultPage />} />
          <Route path="/utfor" element={<ExecutePage />} />
        </Routes>
      </MemoryRouter>,
    );
    await user.click(await screen.findByRole("button", { name: /Bestäm åt mig/i }));
    expect(await screen.findByRole("heading", { name: /Pasta/i })).toBeInTheDocument();
    expect(api.decide).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /^Välj$/i }));
    await waitFor(() => expect(api.acceptDecision).toHaveBeenCalled());
    expect(await screen.findByText("Koka pasta.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Till Hem/i })).toBeInTheDocument();
  });
});

describe("Lista", () => {
  beforeEach(() => {
    clearAuth();
    localStorage.clear();
  });

  it("adds and toggles shopping items", async () => {
    const user = userEvent.setup();
    const { api } = await import("../lib/api");
    render(
      <MemoryRouter>
        <ListaPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/mjölk/i)).toBeInTheDocument();
    const box = screen.getByRole("textbox");
    await user.clear(box);
    await user.type(box, "bröd");
    await user.click(screen.getByRole("button", { name: /lägg/i }));
    await waitFor(() => expect(api.addShopping).toHaveBeenCalledWith("bröd"));
    await user.click(screen.getByRole("checkbox"));
    await waitFor(() => expect(api.toggleShopping).toHaveBeenCalled());
  });
});

describe("Auth", () => {
  beforeEach(() => {
    clearAuth();
    localStorage.clear();
  });

  it("login/logout guest path", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AuthPage />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: /Logga in/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Fortsätt som gäst/i }));
  });
});

describe("ErrorBoundary", () => {
  it("shows Swedish error card instead of white screen", () => {
    const Boom = () => {
      throw new Error("boom");
    };
    // Suppress expected error noise
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/Något gick snett/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Försök igen/i })).toBeInTheDocument();
    spy.mockRestore();
  });
});
