import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Provider, useSelector } from 'react-redux';
import { store } from './store';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import NotebookWorkspace from './pages/NotebookWorkspace';

class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(e) { return { error: e }; }
  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center flex-col gap-4 p-8" style={{ background: '#FEF2F2' }}>
          <div className="text-lg font-bold" style={{ color: '#991B1B' }}>Something went wrong</div>
          <pre className="max-w-2xl overflow-auto p-4 rounded-lg text-sm" style={{ background: '#fff', border: '1px solid #FCA5A5', color: '#7F1D1D', whiteSpace: 'pre-wrap' }}>
            {this.state.error?.message}
          </pre>
          <button onClick={() => { this.setState({ error: null }); window.location.href = '/dashboard'; }}
            className="px-5 py-2 rounded-lg text-sm font-semibold" style={{ background: '#DC2626', color: '#fff' }}>
            Back to Dashboard
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function PrivateRoute({ children }) {
  const user = useSelector(s => s.app.user);
  const token = localStorage.getItem('ag_token');
  return user || token ? children : <Navigate to="/" replace />;
}

function AppRoutes() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/dashboard" element={<PrivateRoute><DashboardPage /></PrivateRoute>} />
          <Route path="/notebook/:id" element={<PrivateRoute><ErrorBoundary><NotebookWorkspace /></ErrorBoundary></PrivateRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  );
}

function App() {
  return (
    <Provider store={store}>
      <AppRoutes />
    </Provider>
  );
}

export default App;
