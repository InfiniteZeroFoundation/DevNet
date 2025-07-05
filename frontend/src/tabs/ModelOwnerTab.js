
import React, { useState, useEffect, useContext } from "react";
import { TooltipContext } from "../context/TooltipContext";



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


export default function ModelOwnerTab({ fetchGIState, GIstate, GIstatedes }) {
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
