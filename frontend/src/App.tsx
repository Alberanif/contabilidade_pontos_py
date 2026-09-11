import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Registros from "./pages/Registros";
import Contabilidade from "./pages/Contabilidade";
import Fila from "./pages/Fila";
import Desafios from "./pages/Desafios";
import CoachesPorCla from "./pages/CoachesPorCla";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/registros" element={<Registros />} />
          <Route path="/fila" element={<Fila />} />
          <Route path="/contabilidade" element={<Contabilidade />} />
          <Route path="/desafios" element={<Desafios />} />
          <Route path="/coaches-por-cla" element={<CoachesPorCla />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
