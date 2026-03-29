import { useState } from "react";
import LoginPage from "@/components/LoginPage";
import Dashboard from "@/pages/Dashboard";

const Index = () => {
  const [loggedIn, setLoggedIn] = useState(false);

  if (!loggedIn) {
    return <LoginPage onLogin={() => setLoggedIn(true)} />;
  }

  return <Dashboard onLogout={() => setLoggedIn(false)} />;
};

export default Index;
