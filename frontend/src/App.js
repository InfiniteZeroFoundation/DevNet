import logo from './logo.svg';
import './App.css';
import React, { useState, useEffect, useContext } from "react";
import { TooltipProvider, TooltipContext } from "./context/TooltipContext"; 


/** ======================= TAB BAR ======================= */
function TabBar({ activeTab, setActiveTab }) {
  // We include a 'validator' tab
  const tabs = ["DINDAO", "ModelOwner", "Validators", "Clients" ];
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

/** ======================= DINDAO TAB ======================= */
function DINDAO() {

  const [loading, setLoading] = useState(true);
  const { showTooltip } = useContext(TooltipContext);
  const [dincordinator_address, setDincoordinatorAddress] = useState(null);
  const [dintoken_address, setDintokenAddress] = useState(null);
  const [DINDAORepresentative_address, setDINDAORepresentativeAddress] = useState(null);
  const [DINDAORepresentative_Eth_balance, setDINDAORepresentativeEthBalance] = useState(null);
  const [DINCoordinator_Eth_balance, setDINCoordinatorEthBalance] = useState(null);

  const deployDINCoordinator = async () => {
    try {
      const response = await fetch("http://localhost:8000/dindao/deployDINCoordinator", { method: "POST" });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log(data.message);
      
      // Show tooltip
      if (data.status === "success") {
        setDincoordinatorAddress(data.dincordinator_address);
        setDintokenAddress(data.dintoken_address);
        setDINDAORepresentativeAddress(data.DINDAORepresentative_address);
        setDINDAORepresentativeEthBalance(data.DINDAORepresentative_Eth_balance);
        setDINCoordinatorEthBalance(data.DINCoordinator_Eth_balance);
        
        showTooltip(data.message, false);
      } else {
        showTooltip(data.message, true);
        setDincoordinatorAddress(null);
        setDintokenAddress(null);
        setDINDAORepresentativeAddress(null);
        setDINDAORepresentativeEthBalance(null);
      }
    } catch (err) {
      console.error("Error creating DINDAO:", err);
      // Show error tooltip
      showTooltip(err.message, true);
    }
  };

  const fetchDINDAOState = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/dindao/getDINDAOState", { method: "POST" });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log("Initial DINDAO state:", data);
      setDincoordinatorAddress(data.dincordinator_address);
      setDintokenAddress(data.dintoken_address);
      setDINDAORepresentativeAddress(data.DINDAORepresentative_address);
      setDINDAORepresentativeEthBalance(data.DINDAORepresentative_Eth_balance);
      setDINCoordinatorEthBalance(data.DINCoordinator_Eth_balance);
    
    } catch (err) {
      console.error("Error fetching DINDAO state:", err);
      // Optionally show an error tooltip
      showTooltip(err.message, true);
      setDincoordinatorAddress(null);
      setDintokenAddress(null);
      setDINDAORepresentativeAddress(null);
      setDINDAORepresentativeEthBalance(null);
      setDINCoordinatorEthBalance(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDINDAOState(); // Call the function when the component mounts
  },[]); // Add dependencies if necessary (e.g., showTooltip)

  return (
    <div className="tab-content">
      <h2>DINDAO</h2>
      {loading ? (
        <div>Loading...</div>
      ) : (
        <>
        <div>
            <h3>DINDAO Representative Address: {DINDAORepresentative_address}</h3>
            <h3>DINDAO Representative ETH Balance: {DINDAORepresentative_Eth_balance}</h3>
            <h3>DINCoordinator Address: {dincordinator_address || "Not Available"}</h3>
            <h3>DINToken Address: {dintoken_address || "Not Available"}</h3>
            <h3>DINCoordinator ETH Balance: {DINCoordinator_Eth_balance ?? "Not Available"}</h3>
            {!dincordinator_address && (
              <button
                className="button button--primary"
                onClick={deployDINCoordinator}
                style={{ marginTop: "1rem" }}
              >
                Deploy DINCoordinator
              </button>
            )}
            <button
              className="button"
              onClick={fetchDINDAOState}
              style={{ marginTop: "1rem", marginLeft: "1rem" }}
            >
              Refresh State
            </button>
          </div>
        </> 
      )}
    </div>
  );
}

/** ======================= ModelOwner TAB ======================= */
function ModelOwnerTab() {
  const [loading, setLoading] = useState(true);
  const { showTooltip } = useContext(TooltipContext);

  const [modelOwnerAddress, setModelOwnerAddress] = useState(null); 
  const [modelOwnerEthBalance, setModelOwnerEthBalance] = useState(null); 
  const [modelOwnerDintokenBalance, setModelOwnerDintokenBalance] = useState(null);
  const [dintaskcoordinatorAddress, setDintaskcoordinatorAddress] = useState(null);
  const [dintaskcoordinatorDintokenBalance, setDintaskcoordinatorDintokenBalance] = useState(null);
  const [genesisModelSetF, setGenesisModelF] = useState(false);
  const [genesisModelIpfsHash, setGenesisModelIpfsHash] = useState(null);



  const fetchModelOwnerState = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/getModelOwnerState", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Fetched model owner state:", data);

      setModelOwnerAddress(data.model_owner_address);
      setModelOwnerEthBalance(data.model_owner_eth_balance);
      setModelOwnerDintokenBalance(data.model_owner_dintoken_balance);

      setDintaskcoordinatorAddress(data.dintaskcoordinator_address);
      setDintaskcoordinatorDintokenBalance(data.dintaskcoordinator_dintoken_balance);

      setGenesisModelF(data.IS_GenesisModelCreated);
      setGenesisModelIpfsHash(data.model_ipfs_hash);
    } catch (err) {
      console.error("Error fetching model owner state:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const deployDINTaskCoordinator = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/deployDINTaskCoordinator", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Deployed DINTaskCoordinator:", data);
      setDintaskcoordinatorAddress(data.dintaskcoordinator_contract_address);
      setDintaskcoordinatorDintokenBalance(data.dintaskcoordinator_dintoken_balance);
      showTooltip(data.message, false);
    } catch (err) {
      console.error("Error deploying DINTaskCoordinator:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const createGenesisModel = async () => {
    
  }

  const depositAndMintDINTokens = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/depositAndMintDINTokens", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      setModelOwnerDintokenBalance(data.model_owner_dintoken_balance);
      setModelOwnerEthBalance(data.model_owner_eth_balance);
    } catch (err) {
      console.error("Error depositing and minting DIN tokens:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }


  const depositRewardInDINTaskCoordinator = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/depositRewardInDINTaskCoordinator", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      setDintaskcoordinatorDintokenBalance(data.dintaskcoordinator_dintoken_balance);
      setModelOwnerDintokenBalance(data.model_owner_dintoken_balance);
      setModelOwnerEthBalance(data.model_owner_eth_balance);
    } catch (err) {
      console.error("Error depositing reward in DINTaskCoordinator:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchModelOwnerState();
  }, []);


  return (
    <div className="tab-content">
      <h2>ModelOwner</h2>
      {loading ? (
        <div>Loading...</div>
      ) : (
        <>
          <div>
            <h3>Model Owner Address: {modelOwnerAddress}</h3>
            <h3>Model Owner ETH Balance: {modelOwnerEthBalance}</h3>
            <h3>Model Owner DINToken Balance: {modelOwnerDintokenBalance}</h3>
          </div>

          <div style={{ marginTop: "1rem" }}>
            <button className="button button--primary" onClick={depositAndMintDINTokens}>
              Deposit and Mint DIN Tokens
            </button>
          </div>

          <div style={{ marginTop: "1rem" }}>
            {dintaskcoordinatorAddress ? (
              <>
                <h3>DINTaskCoordinator Address: {dintaskcoordinatorAddress}</h3>
                <h3>DINToken in DINTaskCoordinator: {dintaskcoordinatorDintokenBalance}</h3>
                <button className="button button--primary" onClick={depositRewardInDINTaskCoordinator}>
                Deposit Reward in DINTaskCoordinator : 1 M
              </button>
              </>
            ) : (
              <button className="button button--primary" onClick={deployDINTaskCoordinator}>
                Deploy DINTaskCoordinator
              </button>
            )}
          </div>

          <div style={{ marginTop: "1rem" }}>
            {genesisModelSetF ? (
              <>
                <h3>Genesis Model Created</h3>
                <p>Genesis Model IPFS Hash: {genesisModelIpfsHash}</p>
              </>
            ) : (
              <button className="button button--primary" onClick={createGenesisModel}>
                Create Genesis Model
              </button>
            )}
          </div>
          
        </>
      )}
      
    </div>
  );
}

/** ======================= Clients TAB ======================= */
function ClientsTab() {

  const [clientModelsCreatedF, setClientModelsCreatedF] = useState(false);
  const [client_model_ipfs_hashes, setClientModelIpfsHashes] = useState([]);
  const [clients_address, setClientsAddress] = useState([]);
  const { showTooltip } = useContext(TooltipContext);
  const [loading, setLoading] = useState(true);
  // differential privacy state 
  const [DPMode, setDPMode] = useState("afterTraining"); 
  // Possible values: "afterTraining", "disabled"
  //"beforeTraining" is not supported for now

  useEffect(() => {
    const fetchClientModelState = async () => {
      try {
        const response = await fetch("http://localhost:8000/clients/getClientModelsCreatedF", { 
          method: "POST",
        });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        console.log(data);
        console.log("Initial clientModelsCreatedF state:", data.client_models_created_f);
        setClientModelsCreatedF(data.client_models_created_f);
        setClientModelIpfsHashes(data.client_model_ipfs_hashes);
        setClientsAddress(data.client_addresses);
        setLoading(false);
      } catch (err) {
        console.error("Error fetching clientModelsCreatedF state:", err);
        showTooltip(err.message, true);
      }
    };

    fetchClientModelState();
  }, []);

  const createClientModels = async () => {
    try {
      const response = await fetch("http://localhost:8000/clients/createClientModels", { 
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          DPMode: DPMode,
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log(data);
      
      // Show tooltip
      if (data.status === "success") {
        setClientModelsCreatedF(data.client_models_created_f);
        setClientsAddress(data.client_addresses);
        setClientModelIpfsHashes(data.client_model_ipfs_hashes);
        showTooltip(data.message, false);
      } else {
        showTooltip(data.message, true);
      }
    } catch (err) {
      console.error("Error creating client models:", err);
      // Show error tooltip
      showTooltip(err.message, true);
    }
  };

  return (
    <div className="tab-content">
      <h2>Clients</h2>
      {loading ? (
        <div>Loading...</div>
      ) : (
        <>
        {/* Conditionally render DP selection or just display current mode */}
        {!clientModelsCreatedF ? (
          <div>
            <label htmlFor="DPMode">Differential Privacy Mode:</label>
            <select
              id="DPMode"
              value={DPMode}
              onChange={(e) => setDPMode(e.target.value)}
            >
              <option value="disabled">Disabled</option>
              {/* <option value="beforeTraining">Before Training</option> */}
              <option value="afterTraining">After Training</option>
            </select>
          </div>
        ) : (
          <div>
            <h3>Differential Privacy Mode:</h3>
            <p>{DPMode}</p>
          </div>
        )}

        {/* Client Models Display */}
        {clientModelsCreatedF ? (
        <div>
          <h3>Client Models Available</h3>
          {clients_address && clients_address.length > 0 ? (
            clients_address.map((address, index) => (
              <p key={index}>
                {address} : {client_model_ipfs_hashes[index]}
              </p>
            ))
          ) : (
            <p>No client models available.</p>
          )}
        </div>
      ) : (
        <div>
          <h3>Client Models Not Available</h3>
          <button className="button button--primary" onClick={() => createClientModels()} style={{ marginTop: "1rem" }}>Create Client Models</button>
        </div>
        )}
        </> 
      )}
      
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
  const [activeTab, setActiveTab] = useState("DINDAO");
  const { tooltipVisible, tooltipMsg, tooltipClass, hideTooltip, showTooltip } = useContext(TooltipContext);
  const [GI,setGI] = useState(0);
  const [GIstate, setGIstate] = useState("started");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchGIState = async () => {
      try {
        const response = await fetch("http://localhost:8000/modelowner/getGIState");
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        console.log(data);
        setGI(data.GI);
        setGIstate(data.GIstate);
        setLoading(false);
      } catch (err) {
        console.error("Error fetching GI state:", err);
        showTooltip(err.message, true);
      }
    };

    fetchGIState();
  }, [activeTab]);


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
          <button onClick={hideTooltip} className="tooltip-close">
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

          {loading ? (
            <div>Loading...</div>
          ) : (
            <>
            <div style={{ marginTop: "1rem", marginBottom: "1rem" }}>
              <h3>Global Iteration: {GI}</h3>
              <h3>Global Iteration State: {GIstate}</h3>
            </div>
            </>
          )}
            
          <TabBar activeTab={activeTab} setActiveTab={setActiveTab} />
          {activeTab === "DINDAO" && <DINDAO />}
          {activeTab === "ModelOwner" && <ModelOwnerTab />}
          {activeTab === "Validators" && <ValidatorsTab />}
          {activeTab === "Clients" && <ClientsTab />}
        </div>
      </main>

      <footer className="footer">
        <p>&copy; 2025 DIN MVP</p>
      </footer>
    </div>
  );
}

export default App;
