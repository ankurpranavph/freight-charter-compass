import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import Forecast from "./pages/Forecast";
import Recommendation from "./pages/Recommendation";
import DataSources from "./pages/DataSources";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="forecast" element={<Forecast />} />
          <Route path="recommend" element={<Recommendation />} />
          <Route path="data-sources" element={<DataSources />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
