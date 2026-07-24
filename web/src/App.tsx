import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { AppShell } from "./layout/AppShell";
import { AuthPage } from "./pages/AuthPage";
import { ClothesPage } from "./pages/ClothesPage";
import { ExecutePage } from "./pages/ExecutePage";
import { FridgePage } from "./pages/FridgePage";
import { HomePage } from "./pages/HomePage";
import { ListaPage } from "./pages/ListaPage";
import { HistorikPage } from "./pages/HistorikPage";
import { ProfilPage } from "./pages/ProfilPage";
import { ResultPage } from "./pages/ResultPage";
import "./styles/global.css";

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<HomePage />} />
            <Route path="lista" element={<ListaPage />} />
            <Route path="historik" element={<HistorikPage />} />
            <Route path="profil" element={<ProfilPage />} />
            <Route path="login" element={<AuthPage />} />
            <Route path="klader" element={<ClothesPage />} />
            <Route path="kylen" element={<FridgePage />} />
            <Route path="resultat" element={<ResultPage />} />
            <Route path="utfor" element={<ExecutePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
