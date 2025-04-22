import logo from './logo.svg';
import './App.css';
import React, { useState, useEffect } from "react";


/** ======================= TAB BAR ======================= */
function TabBar({ activeTab, setActiveTab }) {
  // We include a 'validator' tab
  const tabs = ["ModelOwner", "Clients", "Validators"];
  return (
    <div className="tab-bar">
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => setActiveTab(tab)}
          className={activeTab === tab ? "tab-button active" : "tab-button"}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

/** ======================= ModelOwner TAB ======================= */
function ModelOwnerTab() {
  const [genesisModelF, setGenesisModelF] = useState(false);
  
  const createGenesisModel = async () => {
    try {
      const response = await fetch("http://localhost:8000/modelowner/createGenesisModel");
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log(data.message);

      // Show tooltip
      if (data.status === "success") {
        setGenesisModelF(true);
        showTooltip(data.message, false);
      } else {
        showTooltip(data.message, true);
      }
    } catch (err) {
      console.error("Error creating genesis model:", err);
      // Show error tooltip
      showTooltip(err.message, true);
    }
  };
  
  return (
    <div className="tab-content">
      <h2>ModelOwner</h2>
      {genesisModelF ? (
        <div>
          <h3>Genesis Model Available</h3>
        </div>
      ) : (
        <div>
          <h3>Genesis Model Not Available</h3>
          <button className="button button--primary" onClick={() => createGenesisModel()}>Create Genesis Model</button>
        </div>
      )}
    </div>
  );
}

/** ======================= Clients TAB ======================= */
function ClientsTab() {
  return (
    <div className="tab-content">
      <h2>Clients</h2>
    </div>
  );
}

/** ======================= Validator TAB ======================= */
function ValidatorsTab() {
  return (
    <div className="tab-content">
      <h2>Validators</h2>
    </div>
  );
}



function App() {
  const [activeTab, setActiveTab] = useState("ModelOwner");
  const [tooltipMsg, setTooltipMsg] = useState("");
  const [tooltipVisible, setTooltipVisible] = useState(false);
  const [tooltipTimeout, setTooltipTimeout] = useState(null);
  const [tooltipClass, setTooltipClass] = useState("");


  // Function to show tooltip with dynamic content and styling
  const showTooltip = (message, isError) => {
    setTooltipMsg(message); // Set the message content
    setTooltipClass(isError ? "message--error" : "message--success"); // Set the class (red/green)
    setTooltipVisible(true); // Show the tooltip

    // Clear any existing timeout to avoid conflicts
    if (tooltipTimeout) {
      clearTimeout(tooltipTimeout); // Cancel the previous timeout
    }

    // Set a new timeout to hide the tooltip after 3 seconds
    const timeoutId = setTimeout(() => {
      setTooltipVisible(false); // Hide the tooltip
      setTooltipTimeout(null); // Clear the reference to the timeout ID
    }, 3000);

    // Save the new timeout ID in the state
    setTooltipTimeout(timeoutId);
  };


  const handleResetAll = async () => {
    try {
      const response = await fetch("http://localhost:8000/reset/resetall");
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log(data.message);

      // Show tooltip
      if (data.status === "success") {
        showTooltip(data.message, false);
      } else {
        showTooltip(data.message, true);
      }

      // Reload the page after 1 second
      setTimeout(() => {
        window.location.reload();
      }, 1000);
    } catch (err) {
      console.error("Error resetting all:", err);
      // Show error tooltip
      showTooltip(err.message, true);
    }
  };

  const handleDistributeDataset = async () => {
    try {
      const response = await fetch("http://localhost:8000/distribute/dataset");
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log(data.message);

      // Show tooltip
      if (data.status === "success") {
        showTooltip(data.message, false);
      } else {
        showTooltip(data.message, true);
      }
    } catch (err) {
      console.error("Error distributing dataset:", err);
      // Show error tooltip
      showTooltip(err.message, true);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>DIN MVP</h1>
        <nav className="navbar">
          <ul>
            {/* Add external links if desired */}
            <li>
              <a href="https://github.com/">GitHub</a>
            </li>
            <li>
              <a href="https://github.com/Doctelligence/DINv1MVC/blob/master/Documentation.md">Documentation</a>
            </li>
          </ul>
        </nav>
      </header>
      {/* Tooltip */}
      {tooltipVisible && (
        <div className={`tooltip ${tooltipClass}`} style={{ marginTop: "1rem", marginBottom: "1rem" }}>
          <span>{tooltipMsg}</span>
          <button className="tooltip-close" onClick={() => setTooltipVisible(false)}>
            &times;
          </button>
        </div>
      )}
      <main className="main-content">
        <div className="container" style={{ marginTop: "1rem", marginBottom: "1rem" }}>
          <div style={{ marginTop: "1rem", marginBottom: "1rem" }}>
            <button className="button button--danger" onClick={handleResetAll}>
              Reset All
            </button>
            <button
              className="button button--primary" 
              style={{ marginLeft: "1rem" }} 
              onClick={handleDistributeDataset}
            >
              Distribute Dataset
            </button>
          </div>
          <TabBar activeTab={activeTab} setActiveTab={setActiveTab} />
          {activeTab === "ModelOwner" && <ModelOwnerTab />}
          {activeTab === "Clients" && <ClientsTab />}
          {activeTab === "Validators" && <ValidatorsTab />}
        </div>
      </main>

      <footer className="footer">
        <p>&copy; 2025 DIN MVP</p>
      </footer>
    </div>
  );
}

export default App;
