import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Menu, X, Bell, Settings, User, LogOut } from 'lucide-react';
import { useAuthStore } from '../../store/useAuthStore';
import './Navbar.css';

export default function Navbar() {
  const location = useLocation();
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const isActive = (path: string) => location.pathname === path;

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <nav className="navbar">
      <div className="navbar-container">
        {/* Logo */}
        <Link to="/dashboard" className="navbar-logo">
          <span className="logo-icon">₹</span>
          <span className="logo-text">FinSage</span>
        </Link>

        {/* Desktop Menu */}
        <div className="navbar-menu desktop-only">
          <Link 
            to="/dashboard" 
            className={`nav-link ${isActive('/dashboard') ? 'active' : ''}`}
          >
            Dashboard
          </Link>
          <Link 
            to="/tax-analysis" 
            className={`nav-link ${isActive('/tax-analysis') ? 'active' : ''}`}
          >
            Tax Analysis
          </Link>
          <Link 
            to="/compliance" 
            className={`nav-link ${isActive('/compliance') ? 'active' : ''}`}
          >
            Compliance
          </Link>
          <Link 
            to="/reports" 
            className={`nav-link ${isActive('/reports') ? 'active' : ''}`}
          >
            Reports
          </Link>
        </div>

        {/* Actions */}
        <div className="navbar-actions">
          <button className="icon-btn" aria-label="Notifications">
            <Bell size={20} />
            <span className="notification-badge">3</span>
          </button>
          
          <button className="icon-btn" aria-label="Settings">
            <Settings size={20} />
          </button>

          <div className="user-menu">
            <button className="user-avatar">
              <User size={20} />
            </button>
            <div className="dropdown-menu">
              <Link to="/profile">Profile</Link>
              <Link to="/settings">Settings</Link>
              <hr />
              <button className="logout-btn" onClick={handleLogout}>
                <LogOut size={16} />
                Logout
              </button>
            </div>
          </div>

          {/* Mobile Menu Toggle */}
          <button 
            className="mobile-menu-btn"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
      </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="mobile-menu">
          <Link to="/dashboard" className="mobile-nav-link" onClick={() => setMobileMenuOpen(false)}>Dashboard</Link>
          <Link to="/tax-analysis" className="mobile-nav-link" onClick={() => setMobileMenuOpen(false)}>Tax Analysis</Link>
          <Link to="/compliance" className="mobile-nav-link" onClick={() => setMobileMenuOpen(false)}>Compliance</Link>
          <Link to="/reports" className="mobile-nav-link" onClick={() => setMobileMenuOpen(false)}>Reports</Link>
          <Link to="/itr-guide" className="mobile-nav-link" onClick={() => setMobileMenuOpen(false)}>ITR Guide</Link>
          <Link to="/health-score" className="mobile-nav-link" onClick={() => setMobileMenuOpen(false)}>Health Score</Link>
        </div>
      )}
    </nav>
  );
}
