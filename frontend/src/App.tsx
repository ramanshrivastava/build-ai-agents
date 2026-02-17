import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { MotionConfig } from "motion/react";
import { PatientsPage } from "@/pages/PatientsPage";

function App() {
  return (
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/patients" replace />} />
          <Route path="/patients/:id?" element={<PatientsPage />} />
        </Routes>
      </BrowserRouter>
    </MotionConfig>
  );
}

export default App;
