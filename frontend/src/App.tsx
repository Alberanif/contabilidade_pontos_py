import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Registros from "./pages/Registros";
import Contabilidade from "./pages/Contabilidade";
import Desafios from "./pages/Desafios";
import CoachesPorCla from "./pages/CoachesPorCla";
import Login from "./pages/Login";
import TrocarSenha from "./pages/TrocarSenha";
import Usuarios from "./pages/Usuarios";
import { AuthProvider } from "./auth/AuthContext";
import ProtectedRoute from "./auth/ProtectedRoute";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/registros" element={<Registros />} />
              <Route path="/contabilidade" element={<Contabilidade />} />
              <Route path="/desafios" element={<Desafios />} />
              <Route path="/coaches-por-cla" element={<CoachesPorCla />} />
              {/* #61 troca o componente desta rota */}
              <Route path="/trocar-senha" element={<TrocarSenha />} />
              <Route element={<ProtectedRoute requireAdmin />}>
                {/* #62 troca o componente desta rota */}
                <Route path="/usuarios" element={<Usuarios />} />
              </Route>
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
