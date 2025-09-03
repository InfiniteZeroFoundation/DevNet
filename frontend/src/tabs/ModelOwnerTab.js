
import React, { useState, useEffect, useContext } from "react";
import { TooltipContext } from "../context/TooltipContext";
import AuditBatchMO from "../components/AuditBatchMO"
import ModelList from "../components/ModelList"
import ModelAuditTable from "../components/ModelAuditTable"


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


export default function ModelOwnerTab({ fetchGIState, GIstate, GIstatedes, GIstatestr }) {
  const [loading, setLoading] = useState(true);
  const { showTooltip } = useContext(TooltipContext);

  const [modelOwnerAddress, setModelOwnerAddress] = useState(null); 
  const [modelOwnerEthBalance, setModelOwnerEthBalance] = useState(null); 
  const [modelOwnerDintokenBalance, setModelOwnerDintokenBalance] = useState(null);
  const [modelOwnerUSDTBalance, setModelOwnerUSDTBalance] = useState(null);
  const [dintaskcoordinatorAddress, setDintaskcoordinatorAddress] = useState(null);
  const [dintaskauditorAddress, setDintaskauditorAddress] = useState(null);
  const [dintaskauditorDintokenBalance, setDintaskauditorDintokenBalance] = useState(null);
  const [dintaskauditorUSDTBalance, setDintaskauditorUSDTBalance] = useState(null);
  const [MockTetherAddress, setMockTetherAddress] = useState(null);
  const [genesisModelSetF, setGenesisModelF] = useState(false);
  const [genesisModelIpfsHash, setGenesisModelIpfsHash] = useState(null);
  const [registeredTaskValidators, setRegisteredTaskValidators] = useState([]);
  const [clientModelsCreatedF, setClientModelsCreatedF] = useState(false);
  const [lmSubmissions, setLMSubmissions] = useState([]);
  const [registeredTaskAuditors, setRegisteredTaskAuditors] = useState([]);
  const [audiorsBatchTestCIDs, setAudiorsBatchTestCIDs] = useState([]);
  const [TestDataCID_assigned_F, setTestDataCID_assigned_F] = useState(false);
  const [AuditBatches, setAuditBatches] = useState([]);
  const [ModelAuditData, setModelAuditData ] = useState([]);

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

      setGenesisModelF(data.IS_GenesisModelCreated);
      setGenesisModelIpfsHash(data.model_ipfs_hash);
      setRegisteredTaskValidators(data.registered_validators);
      setRegisteredTaskAuditors(data.registered_auditors);
      setClientModelsCreatedF(data.client_models_created_f);
      setModelOwnerUSDTBalance(data.model_owner_usdt_balance);
      setMockTetherAddress(data.mock_tether_address);
      setDintaskauditorAddress(data.dintaskauditor_address);
      setDintaskauditorUSDTBalance(data.dintaskauditor_usdt_balance);
      setDintaskauditorDintokenBalance(data.dintaskauditor_dintoken_balance);
      setAudiorsBatchTestCIDs(data.audiors_batch_test_cids);
      setTestDataCID_assigned_F(data.TestDataCID_assigned_F);
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
      fetchGIState();
      showTooltip(data.message, false);
    } catch (err) {
      console.error("Error deploying DINTaskCoordinator:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const deployDINtaskAuditor = async () => {
    try {
      setLoading(true);

      const response = await fetch("http://localhost:8000/modelowner/deployDINtaskAuditor", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Deployed DINTaskAuditor:", data);
      setDintaskauditorAddress(data.dintaskauditor_contract_address);
      setDintaskauditorDintokenBalance(data.dintaskauditor_dintoken_balance);
      fetchGIState();
      showTooltip(data.message, false);
    } catch (err) {
      console.error("Error deploying DINTaskAuditor:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const depositRewardInDINTaskAuditor = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/depositRewardInDINtaskAuditor", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Deposited reward in DINTaskAuditor:", data);
      setDintaskauditorUSDTBalance(data.dintaskauditor_usdt_balance);
      setModelOwnerUSDTBalance(data.model_owner_usdt_balance);
      fetchGIState();
      showTooltip(data.message, false);
    } catch (err) {
      console.error("Error depositing reward in DINTaskAuditor:", err);
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

  const buyUSDT = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/buyUSDT", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      setModelOwnerEthBalance(data.model_owner_eth_balance);
      setModelOwnerUSDTBalance(data.model_owner_usdt_balance);
    } catch (err) {
      console.error("Error buying usdt:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

  const setDINTaskCoordinatorAsSlasher = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/setDINTaskCoordinatorAsSlasher", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      showTooltip(data.message, false);
      fetchGIState();
    } catch (err) {
      console.error("Error setting DINTaskCoordinator as slasher:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

  const setDINTaskAuditorAsSlasher = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/setDINTaskAuditorAsSlasher", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      showTooltip(data.message, false)
    
      fetchGIState();
    } catch (err) {
      console.error("Error setting DINTaskAuditor as slasher:", err);
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
      fetchGIState();
    } catch (err) {
      console.error("Error starting GI in DINTaskCoordinator:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

  const startDINvalidatorRegistration = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/startDINvalidatorRegistration", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log(data)
      fetchGIState();
    } catch (err) {
      console.error("Error starting DIN validator registration:", err);
    } finally {
      setLoading(false);
    }
  }

  const closeDINvalidatorRegistration = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/closeDINvalidatorRegistration", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      fetchGIState();
    } catch (err) {
      console.error("Error closing DIN validator registration:", err);
    } finally {
      setLoading(false);
    }
  }

  const startDINauditorRegistration = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/startDINauditorRegistration", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      fetchGIState();
    } catch (err) {
      console.error("Error starting DIN auditor registration:", err);
    } finally {
      setLoading(false);
    }
  }

  const closeDINauditorRegistration = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/closeDINauditorRegistration", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      fetchGIState();
    } catch (err) {
      console.error("Error closing DIN auditor registration:", err);
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
      setModelAuditData(data.model_audit_data);
    } catch (err) {
      console.error("Error fetching client models:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }
  
  useEffect(() => {
    fetchModelOwnerState();
    }
  , []);

  useEffect(() => {
    if (clientModelsCreatedF && GIstate >= 11){ //LMSclosed
      fetchClientModels();
    }
  }, [clientModelsCreatedF]);


  const createAuditorsBatches = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/createAuditorsBatches", { method: "POST" });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log(data);
      fetchGIState();
    } catch (err) {
      console.error("Error creating auditors batches:", err);
    } finally {
      setLoading(false);
    }
  }

  const fetchAuditBatches = async () => {
    try {
      setLoading(true); 
      const response = await fetch("http://localhost:8000/modelowner/fetchAuditBatches", { method: "POST" });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log(data);
      setAuditBatches(data.processed_audit_batches);
    } catch (err) {
      console.error("Error fetching audit batches:", err);
    } finally {
      setLoading(false);  
    }
  }

  useEffect(() => {
    if (GIstate >= 12) {
      fetchAuditBatches();
    }
  }, [TestDataCID_assigned_F, GIstate]);

  const createTestSubDatasetsForAuditorsBatches = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/createTestSubDatasetsForAuditorsBatches", { method: "POST" });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log(data);
      fetchGIState();
    } catch (err) {
      console.error("Error creating test sub datasets for auditors batches:", err);
    } finally {
      setLoading(false);
    }
  }

  const startLMsubmissionsEvaluation = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/startLMsubmissionsEvaluation", { method: "POST" });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log(data);
      fetchGIState();
    } catch (err) {
      console.error("Error starting LM submissions evaluation:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

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
      fetchClientModels();
      
      showTooltip(data.message || "Submissions evaluated", false);
    } catch (err) {
      console.error("Error closing LM submissions evaluation:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };
  



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
    if (GIstate >= 15) {
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

  const slashAuditors = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        "http://localhost:8000/modelowner/slashAuditors",
        { method: "POST" }
      );
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  
      const data = await response.json();
      // update balances / state if the backend returns anything
      fetchGIState();          // refresh global state
      console.log(data);
    }
    catch (err) {
      console.error("Error slashing auditors:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

  const slashValidators = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        "http://localhost:8000/modelowner/slashValidators",
        { method: "POST" }
      );
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  
      const data = await response.json();
      // update balances / state if the backend returns anything
      fetchGIState();          // refresh global state
      console.log(data);
      fetchTier1n2Batches();
      showTooltip(data.message || "Validators slashed", false);
    } catch (err) {
      console.error("Error slashing validators:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  };

  const endGI = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        "http://localhost:8000/modelowner/endGI",
        { method: "POST" }
      );
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  
      const data = await response.json();
      // update balances / state if the backend returns anything
      fetchGIState();          // refresh global state
      console.log(data);
      fetchTier1n2Batches();
      showTooltip(data.message || "GI ended", false);
    } catch (err) {
      console.error("Error ending GI:", err);
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
            {MockTetherAddress ? (
              <h3>Model Owner USDT Balance: {modelOwnerUSDTBalance}</h3>
            ) : (
              null
            )}
          </div>

          <div style={{ marginTop: "1rem" }}>
            <button className="button button--primary" onClick={buyUSDT}>
              Buy USDT
            </button>
          </div>

          <div style={{ marginTop: "1rem" }}>
            {dintaskcoordinatorAddress ? (
              <>
                <h3>DINTaskCoordinator Address: {dintaskcoordinatorAddress}</h3>
              </>
            ) : (
              <button className="button button--primary" onClick={deployDINTaskCoordinator}>
                Deploy DINTaskCoordinator
              </button>
            )}
          </div>

          <div style={{ marginTop: "1rem" }}>
            {dintaskcoordinatorAddress ? ( 
              dintaskauditorAddress ? (
                <>
                <h3>DINTaskAuditor Address: {dintaskauditorAddress}</h3>
                <h3>DINToken in DINTaskAuditor: {dintaskauditorDintokenBalance}</h3>
                <h3>USDT in DINTaskAuditor: {dintaskauditorUSDTBalance}</h3>

                <button className="button button--primary" onClick={depositRewardInDINTaskAuditor}>
                Deposit Reward in DINTaskAuditor : 1OOO USDT
                </button>
                </>
              ) : (
                <button className="button button--primary" onClick={deployDINtaskAuditor}>
                  Deploy DINTaskAuditor
                </button>
              )

            ): null}
          </div>

          {  GIstatestr==="AwaitingGenesisModel" ? (
            <div style={{ marginTop: "1rem" }}>
              <button className="button button--primary" onClick={createGenesisModel}>
                Create Genesis Model
              </button>
            </div>) : null

          }

          { GIstatestr==="AwaitingDINTaskCoordinatorAsSlasher" ? (
            <div style={{ marginTop: "1rem" }}>
              <button className="button button--primary" onClick={setDINTaskCoordinatorAsSlasher}>
                Set DINTaskCoordinator as Slasher
              </button>
            </div>) : null

          }

          { GIstatestr==="AwaitingDINTaskAuditorAsSlasher" ? (
            <div style={{ marginTop: "1rem" }}>
              <button className="button button--primary" onClick={setDINTaskAuditorAsSlasher}>
                Set DINTaskAuditor as Slasher
              </button>
            </div>) : null

          }

          <div style={{ marginTop: "1rem" }}>
            {genesisModelSetF ? (
              <>
                <h3>Genesis Model Created</h3>
                <p>Genesis Model IPFS Hash: {genesisModelIpfsHash}</p>
                {GIstatestr === "GenesisModelCreated" || GIstatestr === "GIended" ? (
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


                {GIstatestr === "GIstarted" ? (
                  <>
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={startDINvalidatorRegistration}>
                  Start DIN Validators Registration
                  </button>
                </div>
                  </>
                ):(null)}

                {GIstatestr === "DINvalidatorRegistrationStarted" ? (
                  registeredTaskValidators.length >= 12 ? (
                    <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                      <button className="button button--primary" onClick={closeDINvalidatorRegistration}>
                        Close DIN Validators Registration
                      </button>
                    </div>
                  ) : (
                    <>
                    <p>Not enough validators registered - need at least 12 for demo</p>
                    <p>{registeredTaskValidators.length} Validators registered</p>
                    </>
                  )
                ) : GIstate >= 7 ? (
                  // Assuming GIstate >= 7 means registration is closed or in a later stage // DINvalidatorRegistrationClosed
                  <p>{registeredTaskValidators.length} Validators registered</p>
                ) : null}

                
                {GIstatestr === "DINvalidatorRegistrationClosed" ? (
                  <>
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={startDINauditorRegistration}>
                  Start DIN Auditors Registration
                  </button>
                </div>
                  </>
                ):(null)}

                {GIstatestr === "DINauditorRegistrationStarted" ? (
                  registeredTaskAuditors.length >=9 ? (
                  <>
                    <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                    <button className="button button--primary" onClick={closeDINauditorRegistration}>
                      Close DIN Auditors Registration
                      </button>
                    </div>
                    </>
                  ):(<>
                    <p>Not enough auditors registered - need atleast 9 for demo</p>
                    <p>{registeredTaskAuditors.length} Validators registered</p>
                    </>
                  )
                ): GIstate >= 9 ? (
                  // Assuming GIstate >= 9 means registration is closed or in a later stage // DINauditorRegistrationClosed
                  <p>{registeredTaskAuditors.length} Auditors registered</p>
                ) : null}
              

                {GIstatestr === "DINauditorRegistrationClosed" && registeredTaskValidators.length >=12 && registeredTaskAuditors.length >=9? (
                  <>
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={startLMsubmissions}>
                  Start LM submissions
                  </button>
                </div>
                  </>
                ):(null
                )}

                { GIstatestr === "LMSstarted" && clientModelsCreatedF ? (
                  <>
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={closeLMsubmissions}>
                  Close LM submissions
                  </button>
                </div>
                  </>
                ):null}

                {GIstatestr === "LMSclosed" && (
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                    <button className="button button--primary" onClick={createAuditorsBatches}>
                    Create Auditors Batches
                    </button>
                  </div>
                )}

                {
                  GIstatestr === "AuditorsBatchesCreated" && !TestDataCID_assigned_F && (
                    <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                      <button className="button button--primary" onClick={createTestSubDatasetsForAuditorsBatches}>
                      Create Test Sub Datasets for Auditors Batches
                      </button>
                    </div>
                  )
                }

                {GIstatestr === "AuditorsBatchesCreated"  && TestDataCID_assigned_F && (
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                    <button className="button button--primary" onClick={startLMsubmissionsEvaluation}>
                    Start LM submissions Evaluation
                    </button>
                  </div>
                )}

                { (GIstate >= 11 && GIstate < 13) && clientModelsCreatedF ? ( //LMSclosed
                 <ModelList lm_submissions={lmSubmissions} />
                ) : null}

                { (GIstate >= 12) && clientModelsCreatedF ? ( //AuditorsBatchesCreated
                 <ModelAuditTable 
                 submissions={lmSubmissions} 
                 modelAuditData={ModelAuditData} 
               />
                ) : null}


                { GIstate >=12 && ( //AuditorsBatchesCreated

                    <AuditBatchMO AuditBatches={AuditBatches}/> 
                )}

                

                {GIstatestr === "LMSevaluationStarted" && (
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

                {GIstatestr === "LMSevaluationClosed" && (
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

                {GIstate >=15 && (   //T1nT2Bcreated
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

                {GIstate === 15 && ( // T1nT2Bcreated
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={startT1Aggregation}>
                  Start T1 Aggregation
                  </button>
                  </div>
                )}

                {GIstate === 16 && ( // T1AggregationStarted
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={finalizeT1Aggregation}>
                  Finalize T1 Aggregation
                  </button>
                  </div>
                )}

                {GIstate === 17 && ( // T1AggregationDone
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={startT2Aggregation}>
                  Start T2 Aggregation
                  </button>
                  </div>
                )}

                {GIstate === 18 && ( // T2AggregationStarted
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={finalizeT2Aggregation}>
                  Finalize T2 Aggregation
                  </button>
                  </div>
                )}

                {GIstate === 19 && ( // T2AggregationDone
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={slashAuditors}>
                  Slash Auditors
                  </button>
                  </div>
                )}

                {GIstate === 20 && ( // AuditorsSlashed
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={slashValidators}>
                  Slash Validators
                  </button>
                  </div>
                )}

                {GIstate === 21 && ( // ValidatorSlashed
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={endGI}>
                  End GI
                  </button>
                  </div>
                )}

                
              </>
            ) : (
              null
            )}
          </div>
          
        </>
      )}
      
    </div>
  );
}
