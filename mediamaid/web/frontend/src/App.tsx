import { Routes, Route } from "react-router-dom";
import Nav from "./components/Nav";
import Dashboard from "./pages/Dashboard";
import Records from "./pages/Records";
import Plugins from "./pages/Plugins";
import Config from "./pages/Config";

export default function App() {
  return (
    <>
      <Nav />
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/records" element={<Records />} />
          <Route path="/plugins" element={<Plugins />} />
          <Route path="/config" element={<Config />} />
        </Routes>
      </main>
    </>
  );
}
