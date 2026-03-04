import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import NotebookWorkspace from './pages/NotebookWorkspace';

class ErrorBoundary extends React.Component {
    constructor(props) { super(props); this.state = { error: null }; }
    static getDerivedStateFromError(e) { return { error: e }; }
    render() {
        if (this.state.error) {
            return (
                <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#FEF2F2', flexDirection: 'column', gap: 12, padding: 32 }}>
                    <div style={{ fontSize: 28 }}>⚠️</div>
                    <div style={{ fontWeight: 700, fontSize: 18, color: '#991B1B' }}>Something went wrong</div>
                    <pre style={{ background: '#fff', border: '1px solid #FCA5A5', borderRadius: 8, padding: '12px 18px', fontSize: 13, color: '#7F1D1D', maxWidth: 680, overflowX: 'auto', whiteSpace: 'pre-wrap' }}>
                        {this.state.error?.message}
                        {this.state.error?.stack}
                    </pre>
                    <button onClick={() => { this.setState({ error: null }); window.location.href = '/dashboard'; }}
                        style={{ padding: '8px 20px', background: '#DC2626', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
                        Back to Dashboard
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}

function PrivateRoute({ children }) {
    const user = useSelector(s => s.graph.user);
    const token = localStorage.getItem('ag_token');
    return user || token ? children : <Navigate to="/" replace />;
}

export default function App() {
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
