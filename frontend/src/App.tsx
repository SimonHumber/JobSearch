import { Navigate, Route, Routes } from 'react-router-dom';
import { CompaniesMapPage } from './pages/CompaniesMapPage';
import { JobsPage } from './pages/JobsPage';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<JobsPage />} />
      <Route path="/companies-map" element={<CompaniesMapPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
