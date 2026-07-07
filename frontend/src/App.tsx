import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import TaxAnalysis from './pages/TaxAnalysis';
import Compliance from './pages/Compliance';
import ITRGuide from './pages/ITRGuide';
import HealthScore from './pages/HealthScore';
import Reports from './pages/Reports';
import Settings from './pages/Settings';
import Profile from './pages/Profile';
import SmartSavings from './pages/SmartSavings';
import Login from './pages/Login';
import Signup from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import { ProtectedRoute, PublicOnlyRoute } from './components/auth/RouteGuards';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
        <Route path="/tax-analysis" element={<ProtectedRoute><TaxAnalysis /></ProtectedRoute>} />
        <Route path="/smart-savings" element={<ProtectedRoute><SmartSavings /></ProtectedRoute>} />
        <Route path="/compliance" element={<ProtectedRoute><Compliance /></ProtectedRoute>} />
        <Route path="/itr-guide" element={<ProtectedRoute><ITRGuide /></ProtectedRoute>} />
        <Route path="/health-score" element={<ProtectedRoute><HealthScore /></ProtectedRoute>} />
        <Route path="/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
        <Route path="/login" element={<PublicOnlyRoute><Login /></PublicOnlyRoute>} />
        <Route path="/register" element={<PublicOnlyRoute><Signup /></PublicOnlyRoute>} />
        <Route path="/signup" element={<PublicOnlyRoute><Signup /></PublicOnlyRoute>} />
        <Route path="/forgot-password" element={<PublicOnlyRoute><ForgotPassword /></PublicOnlyRoute>} />
      </Routes>
    </BrowserRouter>
  );
}
