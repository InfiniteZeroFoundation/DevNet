import { useState, useEffect } from "react";

export default function useGIState(showTooltip, activeTab) {
  const [GI, setGI] = useState(0);
  const [GIstate, setGIstate] = useState(0);
  const [GIstatestr, setGIstatestr] = useState("");
  const [GIstatedes, setGIstatedes] = useState("DINTaskCoordinator not deployed");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchGIState = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("http://localhost:8000/getGIState");
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      console.log("Fetched GI state:", data);
      setGI(data.GI);
      setGIstate(data.GIstate);
      setGIstatestr(data.GIstatestr);
      setGIstatedes(data.GIstatedes);
    } catch (err) {
      console.error("Error fetching GI state:", err);
      setError(err);
      if (showTooltip) showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGIState();
  }, [activeTab]);

  return {
    GI,
    GIstate,
    GIstatestr,
    GIstatedes,
    loading,
    error,
    fetchGIState,
  };
}
