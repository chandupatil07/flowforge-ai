import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import NavBar from "./components/NavBar";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import ProjectView from "./pages/ProjectView";
import Workers from "./pages/Workers";

function RequireAuth({ children }: { children: JSX.Element }) {
  const { isAuthed } = useAuth();
  if (!isAuthed) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const { isAuthed } = useAuth();
  return (
    <div className="app-shell">
      {isAuthed && <NavBar />}
      <main className="app-main">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <Dashboard />
              </RequireAuth>
            }
          />
          <Route
            path="/projects/:projectId"
            element={
              <RequireAuth>
                <ProjectView />
              </RequireAuth>
            }
          />
          <Route
            path="/workers"
            element={
              <RequireAuth>
                <Workers />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
