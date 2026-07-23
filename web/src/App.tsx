import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { ExecutePage } from "./pages/ExecutePage";
import { HomePage } from "./pages/HomePage";
import { ListaPage } from "./pages/ListaPage";
import { HistorikPage } from "./pages/HistorikPage";
import { ProfilPage } from "./pages/ProfilPage";
import { ResultPage } from "./pages/ResultPage";
import "./styles/global.css";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="lista" element={<ListaPage />} />
          <Route path="historik" element={<HistorikPage />} />
          <Route path="profil" element={<ProfilPage />} />
          <Route path="resultat" element={<ResultPage />} />
          <Route path="utfor" element={<ExecutePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
