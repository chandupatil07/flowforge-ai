import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function NavBar() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="navbar">
      <Link to="/" className="navbar-brand">
        FlowForge <span>AI</span>
      </Link>
      <nav className="navbar-links">
        <Link to="/">Projects</Link>
        <Link to="/workers">Workers</Link>
      </nav>
      <div className="navbar-user">
        <span>{username}</span>
        <button
          className="btn btn-ghost"
          onClick={() => {
            logout();
            navigate("/login");
          }}
        >
          Log out
        </button>
      </div>
    </header>
  );
}
