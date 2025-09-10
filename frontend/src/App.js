import './App.css';
import React, { useState, useEffect, useContext, useCallback } from "react";
import { TooltipContext } from "./context/TooltipContext"; 

import AppHeader from "./components/AppHeader";
import AppFooter from "./components/AppFooter";
import GlobalActions from "./components/GlobalActions";
import GlobalStateDisplay from "./components/GlobalStateDisplay";
import Tooltip from "./components/Tooltip";
import TabBar from "./components/TabBar";

import TetherFoundationTab from "./tabs/TetherFoundationTab";
import DINDAOTab from "./tabs/DINDAOTab";
import ModelOwnerTab from "./tabs/ModelOwnerTab";
import ClientsTab from "./tabs/ClientsTab";
import ValidatorsTab from "./tabs/ValidatorsTab";
import AuditorsTab from "./tabs/AuditorsTab";
import GlobalAnalyticsTab from "./tabs/GlobalAnalyticsTab";

import useGIState from "./hooks/useGIState";
import { resetAll, distributeDataset } from "./services/global";


export default function App() {

  const [activeTab, setActiveTab] = useState("Tether Foundation");
  const { tooltipVisible, tooltipMsg, tooltipClass, hideTooltip, showTooltip } = useContext(TooltipContext);
  const { GI, GIstate, GIstatestr, GIstatedes, loading, error, fetchGIState } = useGIState(showTooltip, activeTab);

  const [isResetting, setIsResetting] = useState(false);
  const [isDistributing, setIsDistributing] = useState(false);


  const handleResetAll = useCallback(async () => {
    setIsResetting(true);
    try {
      const res = await resetAll();
      showTooltip(res.message, res.status !== "success");
      setTimeout(() => window.location.reload(), 1000);
    } catch (err) {
      showTooltip(err.message, true);
    } finally {
      setIsResetting(false);
    }
  }, [showTooltip]);

  const handleDistributeDataset = useCallback(async () => {
    setIsDistributing(true);
    try {
      const res = await distributeDataset();
      showTooltip(res.message, res.status !== "success");
    } catch (err) {
      showTooltip(err.message, true);
    } finally {
      setIsDistributing(false);
    }
  }, [showTooltip]);

  return (
    <div className="app">
      <AppHeader />
      <Tooltip
        visible={tooltipVisible}
        message={tooltipMsg}
        className={tooltipClass}
        onClose={hideTooltip}
      />
      <main className="main-content">
        <div className="container margin-block">
          <GlobalActions
            onReset={handleResetAll}
            onDistribute={handleDistributeDataset}
            isResetting={isResetting}
            isDistributing={isDistributing}
          />

          <GlobalStateDisplay
            loading={loading}
            error={error}
            GI={GI}
            GIstatedes={GIstatedes}
            fetchGIState = {fetchGIState}
          />
            
          <TabBar activeTab={activeTab} setActiveTab={setActiveTab} />

          {activeTab === "Tether Foundation" && <TetherFoundationTab />}
          {activeTab === "DINDAO" && <DINDAOTab GIstate={GIstate} 
          GI={GI} 
          GIstatestr={GIstatestr}/>}

          {activeTab === "ModelOwner" && <ModelOwnerTab fetchGIState={fetchGIState} GIstate={GIstate} 
          GIstatedes={GIstatedes} 
          GIstatestr={GIstatestr}/>}

          {activeTab === "Validators" && <ValidatorsTab 
          GIstate={GIstate} 
          GI={GI} 
          GIstatestr={GIstatestr}/>}

          {activeTab === "Auditors" && <AuditorsTab 
          GIstate={GIstate} 
          GI={GI} 
          GIstatestr={GIstatestr}/>}

          {activeTab === "Clients" && <ClientsTab 
          GIstate={GIstate} 
          GI={GI} 
          GIstatestr={GIstatestr}/>}

          {activeTab === "Global Analytics" && <GlobalAnalyticsTab GIstate={GIstate} 
          GI={GI} 
          GIstatestr={GIstatestr}/>}

        </div>
      </main>
      <AppFooter />
    </div>
  );
}