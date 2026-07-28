import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { LandingPage } from "./pages/LandingPage";
import { ManualPage } from "./pages/ManualPage";

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/manual" element={<ManualPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
