import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { HomePage } from "./pages/HomePage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { ResultPage } from "./pages/ResultPage";
import "./styles/global.css";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="lista" element={<PlaceholderPage title="Lista" />} />
          <Route path="historik" element={<PlaceholderPage title="Historik" />} />
          <Route path="profil" element={<PlaceholderPage title="Profil" />} />
          <Route path="resultat" element={<ResultPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
