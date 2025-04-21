import logo from './logo.svg';
import './App.css';
import React, { useState, useEffect } from "react";


/** ======================= TAB BAR ======================= */
function TabBar({ activeTab, setActiveTab }) {
  // We include a 'validator' tab
  const tabs = ["ModelOwner", "Clients", "Validator"];
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



function App() {
  const [activeTab, setActiveTab] = useState("ModelOwner");
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
              <a href="https://docs.example.com/">Documentation</a>
            </li>
          </ul>
        </nav>
      </header>

      <main className="main-content">
        <div className="container">
          <TabBar activeTab={activeTab} setActiveTab={setActiveTab} />
        </div>
      </main>

      <footer className="footer">
        <p>&copy; 2025 DIN MVP</p>
      </footer>
    </div>
  );
}

export default App;
