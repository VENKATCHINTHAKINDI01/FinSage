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
import Benefits from './pages/Benefits';
import ChatAssistant from './pages/ChatAssistant';
import Login from './pages/Login';
import Signup from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import Landing from './pages/Landing';
import { ProtectedRoute, PublicOnlyRoute } from './components/auth/RouteGuards';
import PageTransition from './components/common/PageTransition';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public Landing Page — unauthenticated users see this at / */}
        <Route path="/" element={
          <PublicOnlyRoute>
            <PageTransition variant="ocean">
              <Landing />
            </PageTransition>
          </PublicOnlyRoute>
        } />

        {/* Dashboard — authenticated users */}
        <Route path="/dashboard" element={
          <ProtectedRoute>
            <PageTransition variant="warp">
              <Dashboard />
            </PageTransition>
          </ProtectedRoute>
        } />

        {/* Feature Pages */}
        <Route path="/tax-analysis" element={<ProtectedRoute><PageTransition variant="warp"><TaxAnalysis /></PageTransition></ProtectedRoute>} />
        <Route path="/smart-savings" element={<ProtectedRoute><PageTransition variant="warp"><SmartSavings /></PageTransition></ProtectedRoute>} />
        <Route path="/benefits" element={<ProtectedRoute><PageTransition variant="warp"><Benefits /></PageTransition></ProtectedRoute>} />
        <Route path="/assistant" element={<ProtectedRoute><PageTransition variant="warp"><ChatAssistant /></PageTransition></ProtectedRoute>} />
        <Route path="/compliance" element={<ProtectedRoute><PageTransition variant="warp"><Compliance /></PageTransition></ProtectedRoute>} />
        <Route path="/itr-guide" element={<ProtectedRoute><PageTransition variant="warp"><ITRGuide /></PageTransition></ProtectedRoute>} />
        <Route path="/health-score" element={<ProtectedRoute><PageTransition variant="warp"><HealthScore /></PageTransition></ProtectedRoute>} />
        <Route path="/reports" element={<ProtectedRoute><PageTransition variant="warp"><Reports /></PageTransition></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><PageTransition variant="fade"><Settings /></PageTransition></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><PageTransition variant="fade"><Profile /></PageTransition></ProtectedRoute>} />

        {/* Auth Pages */}
        <Route path="/login" element={<PublicOnlyRoute><PageTransition variant="ocean"><Login /></PageTransition></PublicOnlyRoute>} />
        <Route path="/register" element={<PublicOnlyRoute><PageTransition variant="ocean"><Signup /></PageTransition></PublicOnlyRoute>} />
        <Route path="/signup" element={<PublicOnlyRoute><PageTransition variant="ocean"><Signup /></PageTransition></PublicOnlyRoute>} />
        <Route path="/forgot-password" element={<PublicOnlyRoute><PageTransition variant="ocean"><ForgotPassword /></PageTransition></PublicOnlyRoute>} />
      </Routes>
    </BrowserRouter>
  );
}
