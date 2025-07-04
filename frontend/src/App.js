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
  const [DinValidatorStake_address, setDinValidatorStakeAddress] = useState(null);

  const deployDinValidatorStake = async () => {
    try {
      const response = await fetch("http://localhost:8000/dindao/deployDinValidatorStake", { method: "POST" });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log(data.message);
      
      // Show tooltip
      if (data.status === "success") {
        setDinValidatorStakeAddress(data.dinvalidatorstake_address);
        showTooltip(data.message, false);
      } else {
        showTooltip(data.message, true);
        setDinValidatorStakeAddress(null);
      }
    } catch (err) {
      console.error("Error creating DinValidatorStake:", err);
      // Show error tooltip
      showTooltip(err.message, true);
    }
  };

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
      setDinValidatorStakeAddress(data.DINValidatorStake_address);
    
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
            <h3>DinValidatorStake Address: {DinValidatorStake_address || "Not Available"}</h3>
            {dintoken_address && !DinValidatorStake_address && (
              <button
                className="button button--primary"
                onClick={deployDinValidatorStake}
                style={{ marginTop: "1rem" }}
              >
                Deploy DinValidatorStake
              </button>
            )}
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

const thStyle = {border:"1px solid #ccc", padding:"4px", background:"#f7f7f7"};
const tdStyle = {border:"1px solid #eee", padding:"4px"};

const short = addr => addr.slice(0,6)+"…"+addr.slice(-4);
const shorties = arr => arr.map(short).join(", ");

/* ---------- tables ---------- */
function Tier1Table({ rows }) {
  return (
    <Table
      headers={["ID","Validators","Model Idx","Final?","CID"]}
      rows={rows.map(r => [
        r.batch_id,
        shorties(r.validators),
        r.model_indexes.join(", "),
        r.finalized ? "✅" : "⏳",
        r.final_cid || "—"
      ])}/>
  );
}

function Tier2Table({ rows }) {
  return (
    <Table
      headers={["ID","Validators","Final?","CID"]}
      rows={rows.map(r => [
        r.batch_id,
        shorties(r.validators),
        r.finalized ? "✅" : "⏳",
        r.final_cid || "—"
      ])}/>
  );
}

function Table({ headers, rows }) {
  return (
    <table style={{borderCollapse:"collapse", width:"100%"}}>
      <thead>
        <tr>{headers.map(h=>
          <th key={h} style={thStyle}>{h}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((row,i)=>(
          <tr key={i}>
            {row.map((cell,j)=>(
              <td key={j} style={tdStyle}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}


function ModelOwnerTab({ setGIstate, fetchGIState, GIstate, GIstatedes, setGIstatedes }) {
  const [loading, setLoading] = useState(true);
  const { showTooltip } = useContext(TooltipContext);

  const [modelOwnerAddress, setModelOwnerAddress] = useState(null); 
  const [modelOwnerEthBalance, setModelOwnerEthBalance] = useState(null); 
  const [modelOwnerDintokenBalance, setModelOwnerDintokenBalance] = useState(null);
  const [dintaskcoordinatorAddress, setDintaskcoordinatorAddress] = useState(null);
  const [dintaskcoordinatorDintokenBalance, setDintaskcoordinatorDintokenBalance] = useState(null);
  const [genesisModelSetF, setGenesisModelF] = useState(false);
  const [genesisModelIpfsHash, setGenesisModelIpfsHash] = useState(null);
  const [registeredTaskValidators, setRegisteredTaskValidators] = useState([]);
  const [clientModelsCreatedF, setClientModelsCreatedF] = useState(false);
  const [lmSubmissions, setLMSubmissions] = useState([]);

  

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
      setRegisteredTaskValidators(data.registered_validators);
      setClientModelsCreatedF(data.client_models_created_f);
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
      fetchGIState();
      showTooltip(data.message, false);
    } catch (err) {
      console.error("Error deploying DINTaskCoordinator:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const createGenesisModel = async () => {
    try {
      const response = await fetch("http://localhost:8000/modelowner/createGenesisModel", { method: "POST" }); // Assuming this is a POST request
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log(data.message);
      
      // Show tooltip
      if (data.status === "success") {
        setGenesisModelF(data.IS_GenesisModelCreated);
        setGenesisModelIpfsHash(data.model_ipfs_hash);
        fetchGIState();
        showTooltip(data.message, false);
      } else {
        showTooltip(data.message, true);
      }
    } catch (err) {
      console.error("Error creatxing genesis model:", err);
      // Show error tooltip
      showTooltip(err.message, true);
    }
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

  const startGI = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/startGI", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      setModelOwnerEthBalance(data.model_owner_eth_balance);
      fetchGIState();
    } catch (err) {
      console.error("Error starting GI in DINTaskCoordinator:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

  const startLMsubmissions = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/startLMsubmissions", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      fetchGIState();
    } catch (err) {
      console.error("Error starting LM submissions:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

  const closeLMsubmissions = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/closeLMsubmissions", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log(data);
      fetchGIState();
      fetchClientModels();
    } catch (err) {
      console.error("Error closing LM submissions:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }
  
  useEffect(() => {
    fetchModelOwnerState();
    }
  , []);


  const fetchClientModels = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/getClientModels", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log(data);
      setLMSubmissions(data.lm_submissions);
    } catch (err) {
      console.error("Error fetching client models:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

  const approveClientModel = async (clientAddress) => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/approveClientModel", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          client_address: clientAddress,
          approved: true,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log(data);
      fetchClientModels();
    } catch (err) {
      console.error("Error approving client model:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

  const rejectClientModel = async (clientAddress) => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/rejectClientModel", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          client_address: clientAddress,
          approved: false,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log(data);
      fetchClientModels();
    } catch (err) {
      console.error("Error rejecting client model:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (clientModelsCreatedF && GIstate >= 4){
      fetchClientModels();
    }
  }, [clientModelsCreatedF]);

  const closeLMsubmissionsEvaluation = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        "http://localhost:8000/modelowner/closeLMsubmissionsEvaluation",
        { method: "POST" }
      );
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  
      const data = await response.json();
      // update balances / state if the backend returns anything
      fetchGIState();          // refresh global state
      showTooltip(data.message || "Submissions evaluated", false);
    } catch (err) {
      console.error("Error closing LM submissions evaluation:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };
  

  const allLmEvaluated = GIstate >= 4 && lmSubmissions.length > 0 && lmSubmissions.every(s => s[2] === true);

  const [tier1Batches, setTier1Batches] = useState([]);
  const [tier2Batches, setTier2Batches] = useState([]);

  const fetchTier1n2Batches = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/getTier1n2Batches", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log(data);
      setTier1Batches(data.tier1_batches);
      setTier2Batches(data.tier2_batches);
    } catch (err) {
      console.error("Error fetching Tier 1 n 2 Batches:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const createTier1n2Batches = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        "http://localhost:8000/modelowner/createTier1n2Batches",
        { method: "POST" }
      );
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  
      const data = await response.json();
      // update balances / state if the backend returns anything
      fetchGIState();          // refresh global state
      console.log(data);
      fetchTier1n2Batches();
      showTooltip(data.message || "Tier 1 n 2 Batches created", false);
    } catch (err) {
      console.error("Error creating Tier 1 n 2 Batches:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };


  useEffect(() => {
    if (GIstate >= 6) {
      fetchTier1n2Batches();
    }
  }, []);

  const startT1Aggregation = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        "http://localhost:8000/modelowner/startT1Aggregation",
        { method: "POST" }
      );
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  
      const data = await response.json();
      // update balances / state if the backend returns anything
      fetchGIState();          // refresh global state
      console.log(data);
      fetchTier1n2Batches();
      showTooltip(data.message || "Tier 1 Aggregation started", false);
    } catch (err) {
      console.error("Error starting Tier 1 Aggregation:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const finalizeT1Aggregation = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        "http://localhost:8000/modelowner/finalizeT1Aggregation",
        { method: "POST" }
      );
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  
      const data = await response.json();
      // update balances / state if the backend returns anything
      fetchGIState();          // refresh global state
      console.log(data);
      fetchTier1n2Batches();
      showTooltip(data.message || "Tier 1 Aggregation finalized", false);
    } catch (err) {
      console.error("Error finalizing Tier 1 Aggregation:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const startT2Aggregation = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        "http://localhost:8000/modelowner/startT2Aggregation",
        { method: "POST" }
      );
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  
      const data = await response.json();
      // update balances / state if the backend returns anything
      fetchGIState();          // refresh global state
      console.log(data);
      fetchTier1n2Batches();
      showTooltip(data.message || "Tier 2 Aggregation started", false);
    } catch (err) {
      console.error("Error starting Tier 2 Aggregation:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const finalizeT2Aggregation = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        "http://localhost:8000/modelowner/finalizeT2Aggregation",
        { method: "POST" }
      );
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  
      const data = await response.json();
      // update balances / state if the backend returns anything
      fetchGIState();          // refresh global state
      console.log(data);
      fetchTier1n2Batches();
      showTooltip(data.message || "Tier 2 Aggregation finalized", false);
    } catch (err) {
      console.error("Error finalizing Tier 2 Aggregation:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };


  
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
                {GIstate === 1 || GIstate === 11 ? (
                  <>
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={startGI}>
                    Start GI
                  </button>
                </div>
                  </>
                ):(
                <>
                </>
                )}

                {GIstatedes === "GI started" && registeredTaskValidators.length >=12? (
                  <>
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={startLMsubmissions}>
                  Start LM submissions
                  </button>
                </div>
                  </>
                ):(
                <>
                </>
                )}

                { GIstatedes === "LM submissions started" && clientModelsCreatedF ? (
                  <>
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={closeLMsubmissions}>
                  Close LM submissions
                  </button>
                </div>
                  </>
                ):null}

                { (GIstate > 3) && clientModelsCreatedF ? (
                  <div className="client-models-section">
                    <h3>Client Models</h3>

                    {lmSubmissions.map((submission, index) => (
                      <div 
                        key={index} 
                        className="client-model-card"
                        style={{
                          marginTop: "1.5rem",
                          marginBottom: "1.5rem",
                          padding: "1rem",
                          border: "1px solid #ccc",
                          borderRadius: "8px",
                          maxWidth: "600px",
                          marginInline: "auto",
                          boxShadow: "0 2px 6px rgba(0,0,0,0.1)"
                        }}
                      >
                        <p>
                          <strong>Client:</strong> {submission[0]} <br />
                          <strong>Model CID:</strong> {submission[1]}
                        </p>

                        {!submission[2] ? (
                          <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
                            <button
                              className="button button--primary"
                              onClick={() => approveClientModel(submission[0])}
                              style={{
                                backgroundColor: "#10B981",
                                color: "white",
                                fontWeight: "bold",
                                padding: "0.5rem 1rem",
                                borderRadius: "4px",
                                border: "none",
                                cursor: "pointer"
                              }}
                            >
                              Approve Client Model
                            </button>

                            <button
                              className="button button--danger"
                              onClick={() => rejectClientModel(submission[0])}
                              style={{
                                backgroundColor: "#EF4444",
                                color: "white",
                                fontWeight: "bold",
                                padding: "0.5rem 1rem",
                                borderRadius: "4px",
                                border: "none",
                                cursor: "pointer"
                              }}
                            >
                              Reject Client Model
                            </button>
                          </div>
                        ) : (
                          <h4 style={{ textAlign: "center", margin: 0, color: submission[3] ? "green" : "red" }}>
                            {submission[3] ? "✅ Approved" : "❌ Rejected"}
                          </h4>
                        )}
                      </div>
                    ))}
                  </div>
                ) : null}

                {GIstatedes === "LM submissions closed" && allLmEvaluated && (
                  <div
                    style={{
                      marginTop: "1rem",
                      marginBottom: "1rem",
                      display: "flex",
                      justifyContent: "center"
                    }}
                  >
                    <button
                      className="button button--primary"
                      onClick={closeLMsubmissionsEvaluation}
                    >
                      Close LM submissions Evaluation
                    </button>
                  </div>
                )}

                {GIstatedes === "LM submissions evaluation closed" && (
                  <div
                    style={{
                      marginTop: "1rem",
                      marginBottom: "1rem",
                      display: "flex",
                      justifyContent: "center"
                    }}
                  >
                    <button
                      className="button button--primary"
                      onClick={createTier1n2Batches}
                    >
                      Create Tier 1 n 2 Batches
                    </button>
                  </div>
                )}

                {GIstate >=6 && (
                  <>
                  <div style={{ padding: 20, fontFamily: "sans-serif" }}>
                  <h2>DINTaskCoordinator – T1 Batches</h2>
                  {tier1Batches.length ? <Tier1Table rows={tier1Batches}/> : <p>No Tier‑1 batches.</p>}
                  </div>

                  <div style={{ padding: 20, fontFamily: "sans-serif" }}>
                  <h2>DINTaskCoordinator – T2 Batches</h2>
                  {tier2Batches.length ? <Tier2Table rows={tier2Batches}/> : <p>No Tier‑2 batch.</p>}
                  </div>
                  </>
                )}

                {GIstate === 6 && (
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={startT1Aggregation}>
                  Start T1 Aggregation
                  </button>
                  </div>
                )}

                {GIstate === 7 && (
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={finalizeT1Aggregation}>
                  Finalize T1 Aggregation
                  </button>
                  </div>
                )}

                {GIstate === 8 && (
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={startT2Aggregation}>
                  Start T2 Aggregation
                  </button>
                  </div>
                )}

                {GIstate === 9 && (
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={finalizeT2Aggregation}>
                  Finalize T2 Aggregation
                  </button>
                  </div>
                )}

                
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
function ClientsTab({setGIstate, fetchGIState, GIstate, GIstatedes, setGIstatedes}) {

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
          <p>No client models available.</p>
        </div>
        ) : (
          <div>
            <h3>Differential Privacy Mode:</h3>
            <p>{DPMode}</p>

            <h3>Client Models Available</h3>
          {clients_address && clients_address.length > 0 ? (
            clients_address.map((address, index) => (
              <p key={index}>
                {address} : {client_model_ipfs_hashes[index]}
              </p>
            ))
          ): null
          }
          </div>

        )}

        {!clientModelsCreatedF && GIstatedes === "LM submissions started"? (
          <div>
          <h3>Client Models Not Available</h3>
          <button className="button button--primary" onClick={() => createClientModels()} style={{ marginTop: "1rem" }}>Create Client Models</button>
        </div>
        ): null}
        </> 
      )}
    </div>
  );
}

/** ======================= Validator TAB ======================= */
function ValidatorsTab({GIstate, GI, GIstatedes}) {

  const [loading, setLoading] = useState(true);
  const { showTooltip } = useContext(TooltipContext);
  const [validatorAddresses, setValidatorAddresses] = useState([]);
  const [validatorDintokenBalances, setValidatorDintokenBalances] = useState([]);
  const [validatorETHBalances, setValidatorETHBalances] = useState([]);
  const [DINValidatorStakeAddress, setDINValidatorStakeAddress] = useState(null);
  const [validatorDinStakedTokens, setValidatorDinStakedTokens] = useState([]);
  const [dintoken_address, setDintokenAddress] = useState(null);
  const [registeredTaskValidators, setRegisteredTaskValidators] = useState([]);
  const [all_reg_val_t1bs, setAllRegValT1Bs] = useState([]);
  const [all_reg_val_t2bs, setAllRegValT2Bs] = useState([]);
  const [all_reg_val_t1br, setAllRegValT1BR] = useState([]);
  const [all_reg_val_t2br, setAllRegValT2BR] = useState([]);


  const fetchValidatorsState = async () => {
    try {
      const response = await fetch("http://localhost:8000/validators/getValidatorsState", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Fetched validators state:", data);

      setLoading(false);
      setValidatorAddresses(data.validator_addresses);
      setValidatorDintokenBalances(data.validator_dintoken_balances);
      setValidatorETHBalances(data.validator_eth_balances);
      setDINValidatorStakeAddress(data.DINValidatorStakeAddress);
      setValidatorDinStakedTokens(data.validator_din_staked_tokens);
      setDintokenAddress(data.dintoken_address);
      setRegisteredTaskValidators(data.registered_validators);

      if (GIstate >= 7 && GI > 0) {
        setAllRegValT1Bs(data.all_reg_val_assigned_t1_batches)
        setAllRegValT2Bs(data.all_reg_val_assigned_t2_batches)
        setAllRegValT1BR(data.all_res_val_t1)
      }

      if (GIstate >= 9 && GI > 0) {
        setAllRegValT2BR(data.all_res_val_t2)
      }
    } catch (err) {
      console.error("Error fetching validators state:", err);
      showTooltip(err.message, true);
    }
  };

  useEffect(() => {
    fetchValidatorsState();
  }, []);



  const buyDINTokens = async () => {
    try {
      const response = await fetch("http://localhost:8000/validators/buyDINTokens", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Fetched validators state:", data);

      setLoading(false);
      setValidatorAddresses(data.validator_addresses);
      setValidatorDintokenBalances(data.validator_dintoken_balances);
      setValidatorETHBalances(data.validator_eth_balances);
    } catch (err) {
      console.error("Error fetching validators state:", err);
      showTooltip(err.message, true);
    }
  };

  const stakeDINTokens = async () => {
    try {
      const response = await fetch("http://localhost:8000/validators/stakeDINTokens", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Fetched validators state:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchValidatorsState();
      }, 1000);

    } catch (err) {
      console.error("Error fetching validators state:", err);
      showTooltip(err.message, true);
    }
  };

  const stakeDINTokensSingle = async (address) => {
    try {
      const response = await fetch("http://localhost:8000/validators/stakeDINTokensSingle", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          validator_address: address,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("DIN Token Stake done successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchValidatorsState();
      }, 1000);

    } catch (err) {
      console.error("Error staking DIN Tokens:", err);
      showTooltip(err.message, true);
    }
  };

  const buyDINTokensSingle = async (address) => {
    try {
      console.log("Buy DIN Tokens for validator:", address);
      const response = await fetch("http://localhost:8000/validators/buyDINTokensSingle", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          validator_address: address,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Buy DIN Tokens done successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchValidatorsState();
      }, 1000);

    } catch (err) {
      console.error("Error buying DIN Tokens:", err);
      showTooltip(err.message, true);
    }
  };

  const registerTaskValidators = async () => {
    try {
      const response = await fetch("http://localhost:8000/validators/registerTaskValidators", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Task Validators registered successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchValidatorsState();
      }, 1000);

    } catch (err) {
      console.error("Error registering task validators:", err);
      showTooltip(err.message, true);
    }
  };

  const registerTaskValidatorSingle = async (address) => {
    try {
      console.log("Register Task Validator for validator:", address);
      const response = await fetch("http://localhost:8000/validators/registerTaskValidatorSingle", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          validator_address: address,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Register Task Validator done successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchValidatorsState();
      }, 1000);

    } catch (err) {
      console.error("Error registering task validator:", err);
      showTooltip(err.message, true);
    }
  };


  const aggregateHonestlyT1 = async (address) => {
    try {
      console.log("Aggregate Honestly T1 for validator:", address);
      const response = await fetch("http://localhost:8000/validators/aggregateHonestlyT1", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          validator_address: address,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Aggregate Honestly T1 done successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchValidatorsState();
      }, 1000);

    } catch (err) {
      console.error("Error aggregating honestly T1:", err);
      showTooltip(err.message, true);
    }
  };

  const aggregateMaliciouslyT1 = async (address) => {
    try {
      console.log("Aggregate Maliciously T1 for validator:", address);
      const response = await fetch("http://localhost:8000/validators/aggregateMaliciouslyT1", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          validator_address: address,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Aggregate Maliciously T1 done successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchValidatorsState();
      }, 1000);

    } catch (err) {
      console.error("Error aggregating maliciously T1:", err);
      showTooltip(err.message, true);
    }
  };

  const aggregateHonestlyT2 = async (address) => {
    try {
      console.log("Aggregate Honestly T2 for validator:", address);
      const response = await fetch("http://localhost:8000/validators/aggregateHonestlyT2", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          validator_address: address,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Aggregate Honestly T2 done successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchValidatorsState();
      }, 1000);

    } catch (err) {
      console.error("Error aggregating honestly T2:", err);
      showTooltip(err.message, true);
    }
  };

  const aggregateMaliciouslyT2 = async (address) => {
    try {
      console.log("Aggregate Maliciously T2 for validator:", address);
      const response = await fetch("http://localhost:8000/validators/aggregateMaliciouslyT2", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          validator_address: address,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Aggregate Maliciously T2 done successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchValidatorsState();
      }, 1000);

    } catch (err) {
      console.error("Error aggregating maliciously T2:", err);
      showTooltip(err.message, true);
    }
  };

  function ValidatorT1BatchesViewer({
    registeredTaskValidators,
    all_reg_val_t1bs,
    address,
    all_reg_val_t1br
  }) {
    // 1. Find the index of the validator address
    const validatorIndex = registeredTaskValidators.findIndex(
      (a) => a.toLowerCase() === address.toLowerCase()
    );
  
    if (validatorIndex === -1) {
      return <div>Validator address not found.</div>;
    }
  
    // 2. Get the assigned batches for that validator
    const batches = all_reg_val_t1bs[validatorIndex];
  
    return (
      <div>
        <h2>Assigned Tier-1 Batches for {address}</h2>
        {batches.length === 0 ? (
          <p>No batches assigned.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Batch ID</th>
                <th>Validators</th>
                <th>Model Indexes</th>
                <th>Finalized</th>
                <th>Final CID</th>
              </tr>
            </thead>
            <tbody>
              {batches.map((batch, idx) => (
                <tr key={idx}>
                  <td>{batch.batch_id}</td>
                  <td>
                    {batch.validators.map((v) => (
                      <div key={v}>{v}</div>
                    ))}
                  </td>
                  <td>
                    {batch.model_indexes.length
                      ? batch.model_indexes.join(", ")
                      : "—"}
                  </td>
                  <td>{batch.finalized ? "Yes" : "No"}</td>
                  <td>{batch.final_cid || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {GIstate === 7 && batches.length > 0 && !all_reg_val_t1br.includes(address)? (
            <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
            <button
                className="button button--primary"
                onClick={() => aggregateHonestlyT1(address)}
                style={{
                  backgroundColor: "#10B981",
                  color: "white",
                  fontWeight: "bold",
                  padding: "0.5rem 1rem",
                  borderRadius: "4px",
                  border: "none",
                  cursor: "pointer"
                }}
              >
                Aggregate Honestly T1
              </button>
    
              <button
                className="button button--danger"
                onClick={() => aggregateMaliciouslyT1(address)}
                style={{
                  backgroundColor: "#EF4444",
                  color: "white",
                  fontWeight: "bold",
                  padding: "0.5rem 1rem",
                  borderRadius: "4px",
                  border: "none",
                  cursor: "pointer"
                }}
              >
                Aggregate Maliciously T1
              </button>
            </div>
          ) : null}
      </div>
      
    );
  }

  function ValidatorTier2BatchesViewer({
    registeredTaskValidators,
    all_reg_val_t2bs,
    address,
    all_reg_val_t2br
  }) {
    // 1. Find index
    const validatorIndex = registeredTaskValidators.findIndex(
      (a) => a.toLowerCase() === address.toLowerCase()
    );
  
    if (validatorIndex === -1) {
      return <div>Validator address not found.</div>;
    }
  
    // 2. Get the assigned Tier-2 batches
    const batches = all_reg_val_t2bs[validatorIndex];
  
    return (
      <div>
        <h2>Assigned Tier-2 Batches for {address}</h2>
        {batches.length === 0 ? (
          <p>No Tier-2 batches assigned.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Batch ID</th>
                <th>Validators</th>
                <th>Finalized</th>
                <th>Final CID</th>
              </tr>
            </thead>
            <tbody>
              {batches.map((batch, idx) => (
                <tr key={idx}>
                  <td>{batch.batch_id}</td>
                  <td>
                    {batch.validators.map((v) => (
                      <div key={v}>{v}</div>
                    ))}
                  </td>
                  <td>{batch.finalized ? "Yes" : "No"}</td>
                  <td>{batch.final_cid || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {GIstate === 9 && batches.length > 0 && !all_reg_val_t2br.includes(address)? (
            <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
            <button
                className="button button--primary"
                onClick={() => aggregateHonestlyT2(address)}
                style={{
                  backgroundColor: "#10B981",
                  color: "white",
                  fontWeight: "bold",
                  padding: "0.5rem 1rem",
                  borderRadius: "4px",
                  border: "none",
                  cursor: "pointer"
                }}
              >
                Aggregate Honestly T2
              </button>
    
              <button
                className="button button--danger"
                onClick={() => aggregateMaliciouslyT2(address)}
                style={{
                  backgroundColor: "#EF4444",
                  color: "white",
                  fontWeight: "bold",
                  padding: "0.5rem 1rem",
                  borderRadius: "4px",
                  border: "none",
                  cursor: "pointer"
                }}
              >
                Aggregate Maliciously T2
              </button>
            </div>
          ) : null}
      </div>
    );
  }

  return (
    <div className="tab-content">
      <h2>Validators</h2>
      {loading ? (
        <div>Loading...</div>
      ) : (
        <>
        <div>
        <div>
          <h3>Total Registered Validators</h3>
          <p>{registeredTaskValidators.length} Validators</p>
        </div>
          <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "1rem" }}>
            <button className="button button--primary" onClick={() => buyDINTokens()}>Buy DIN Tokens</button>
            {DINValidatorStakeAddress ? (
              <>
              <button className="button button--primary" onClick={() => stakeDINTokens()}>Stake DIN Tokens</button>
              </>
            ) : (
              <p> DIN Validator Stake Contract not deployed</p>
            )}
            {GIstate >=2 ? (
              <button className="button button--primary" onClick={() => registerTaskValidators()}>Register Task Validators </button>
            ) : (
              <></>
            )}
          </div>  
          {validatorAddresses.length > 0 ? (
           validatorAddresses.map((address, index) => (
            <div key={index} className="listbox">
              <p>Address - {address} </p><br/> 
              <p>ETH Balance - {validatorETHBalances[index]} </p><br/> 
              {dintoken_address ? (
                <>
                <p>DIN Token Balance - {validatorDintokenBalances[index]}</p> <br/> 
                </>
              ) : (
                <p>DIN Token Contract not deployed</p>
              )}
              
              <br/>
              {DINValidatorStakeAddress ? (
                <p>Staked DIN Tokens - {validatorDinStakedTokens[index]}</p>
              ) : (
                <p>DIN Validator Stake Contract not deployed</p>
              )}

              { (GIstate >=2)  && GI>0  && registeredTaskValidators.length > 0 && registeredTaskValidators.includes(address) ? (
                <p><span style={{ color: 'green' }}>✅</span> Registered Validator</p>
              ) : (
                <p><span style={{ color: 'red' }}>❌</span> Not Registered Validator</p>
              )}

              {(GIstate >=7)  && GI>0  && registeredTaskValidators.length > 0 && registeredTaskValidators.includes(address) ? (
                <>
                <ValidatorT1BatchesViewer
                registeredTaskValidators={registeredTaskValidators}
                all_reg_val_t1bs={all_reg_val_t1bs}
                address={address}
                all_reg_val_t1br={all_reg_val_t1br}
                />

                <ValidatorTier2BatchesViewer
                registeredTaskValidators={registeredTaskValidators}
                all_reg_val_t2bs={all_reg_val_t2bs}
                address={address}
                all_reg_val_t2br={all_reg_val_t2br}
                />

                </>

              ) : null}
              

              {DINValidatorStakeAddress ? (
                <>
                <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "1rem" }}>
                <button className="button button--primary" onClick={() => buyDINTokensSingle(address)} >Buy DIN Tokens</button>
                </div>
                </>
              ): (<></>)
                }

              {DINValidatorStakeAddress ? (
                <>
                <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "1rem" }}>
                <button className="button button--primary" onClick={() => stakeDINTokensSingle(address)} >Stake DIN Tokens</button>
                </div>
                </>
              ): (<></>)
                }

              { (GIstate >= 2) && GI>0  && (registeredTaskValidators.length > 0 || validatorDinStakedTokens[index] >= 1000000) && registeredTaskValidators.indexOf(address) === -1 ? (
                <>
                <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "1rem" }}>
                <button className="button button--primary" onClick={() =>registerTaskValidatorSingle(address)} >Register Task Validator</button>
                </div>
                </>
              ) : (
                (<></>)
              )}
            </div>
          ))
          ) : (
            <p>No validators available.</p>
          )}
        </div>
        </>
      )}
    </div>
  );
}



function App() {
  const [activeTab, setActiveTab] = useState("DINDAO");
  const { tooltipVisible, tooltipMsg, tooltipClass, hideTooltip, showTooltip } = useContext(TooltipContext);
  const [GI,setGI] = useState(0);
  const [GIstate, setGIstate] = useState(0);
  const [GIstatedes, setGIstatedes] = useState("AwaitingGenesisModel");
  const [loading, setLoading] = useState(true);


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
      setGIstatedes(data.GIstatedes);
      setLoading(false);
    } catch (err) {
      console.error("Error fetching GI state:", err);
      showTooltip(err.message, true);
    }
  };

  useEffect(() => {
    

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
              <h3>Global Iteration State: {GIstatedes}</h3>
            </div>
            </>
          )}
            
          <TabBar activeTab={activeTab} setActiveTab={setActiveTab} />
          {activeTab === "DINDAO" && <DINDAO />}
          {activeTab === "ModelOwner" && <ModelOwnerTab setGIstate={setGIstate} fetchGIState={fetchGIState} GIstate={GIstate} GIstatedes={GIstatedes} setGIstatedes={setGIstatedes}/>}
          {activeTab === "Validators" && <ValidatorsTab GIstate={GIstate} GI={GI} setGIstatedes={setGIstatedes}/>}
          {activeTab === "Clients" && <ClientsTab setGIstate={setGIstate} fetchGIState={fetchGIState} GIstate={GIstate} GIstatedes={GIstatedes} setGIstatedes={setGIstatedes}/>}
        </div>
      </main>

      <footer className="footer">
        <p>&copy; 2025 DIN MVP</p>
      </footer>
    </div>
  );
}

export default App;
