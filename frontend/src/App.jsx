import { useState } from 'react';
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import LiveScan from './pages/LiveScan';
import Provision from './pages/Provision';

function NavBar({ useStubData, onToggleStubData }) {
  const linkClass = ({ isActive }) =>
    `px-4 py-2 rounded transition-colors ${
      isActive
        ? 'bg-green-700 text-white font-semibold'
        : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'
    }`;

  return (
    <nav className="flex items-center gap-2 px-6 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
      <span className="mr-auto font-bold text-green-700 dark:text-green-400 text-lg">
        🌿 Carbon Cost Module
      </span>
      <NavLink to="/provision" className={linkClass}>
        Provision
      </NavLink>
      <NavLink to="/live-scan" className={linkClass}>
        Infrastructure Audit
      </NavLink>
      <NavLink to="/dashboard" className={linkClass}>
        Dashboard
      </NavLink>
      <label className="ml-2 flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input
          type="checkbox"
          checked={useStubData}
          onChange={(e) => onToggleStubData(e.target.checked)}
          className="h-4 w-4 accent-green-600"
        />
        Use stub data
      </label>
    </nav>
  );
}

export default function App() {
  const [useStubData, setUseStubData] = useState(false);

  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100">
        <NavBar useStubData={useStubData} onToggleStubData={setUseStubData} />
        <Routes>
          <Route path="/" element={<Provision />} />
          <Route path="/provision" element={<Provision />} />
          <Route path="/live-scan" element={<LiveScan useStubData={useStubData} />} />
          <Route path="/dashboard" element={<Dashboard useStubData={useStubData} />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
