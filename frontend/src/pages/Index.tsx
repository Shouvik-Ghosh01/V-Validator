import { useAuth } from "@/components/AuthContext";
import Dashboard from "@/pages/Dashboard";

const Index = () => {
  const { logout } = useAuth();
  return <Dashboard onLogout={logout} />;
};

export default Index;
