
import React, { useState, useEffect, useContext } from "react";
import { TooltipContext } from "../context/TooltipContext";
import AuditorTaskCard from "../components/AuditorTaskCard";


/** ======================= Auditors TAB ======================= */
export default function AuditorsTab({GIstate, GI, GIstatestr}) {

  const [loading, setLoading] = useState(true);
  const { showTooltip } = useContext(TooltipContext);
  const [registeredTaskAuditors, setRegisteredTaskAuditors] = useState([]);
  const [auditorAddresses, setAuditorAddresses] = useState([]);
  const [auditorETHBalances, setAuditorETHBalances] = useState([]);
  const [dintoken_address, setDintokenAddress] = useState(null);
  const [DINValidatorStakeAddress, setDINValidatorStakeAddress] = useState(null);
  const [AuditorsDintokenBalances, setAuditorsDintokenBalances] = useState([]);
  const [AuditorsDinStakedTokens, setAuditorsDinStakedTokens] = useState([]);

  const [auditorEvaluationBatches, setAuditorEvaluationBatches] = useState({});


  const fetchAuditorsState = async () => {
    try {
      const response = await fetch("http://localhost:8000/auditors/getAuditorsState", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Fetched auditors state:", data);

      setLoading(false);
      setRegisteredTaskAuditors(data.registered_auditors);
      setAuditorAddresses(data.auditors_addresses);
      setAuditorETHBalances(data.auditors_eth_balances);
      setDintokenAddress(data.dintoken_address);
      setDINValidatorStakeAddress(data.DINValidatorStakeAddress);
      setAuditorsDintokenBalances(data.auditors_dintoken_balances);
      setAuditorsDinStakedTokens(data.auditors_din_staked_tokens);
      
    } catch (err) {
      console.error("Error fetching auditors state:", err);
      showTooltip(err.message, true);
    }
  };

  useEffect(() => {
    fetchAuditorsState();
  }, []);

  const buyDINTokens = async () => {
    try {
      const response = await fetch("http://localhost:8000/auditors/buyDINTokens", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Buy DIN tokens:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchAuditorsState();
      }, 1000);
    } catch (err) {
      console.error("Error buying DIN tokens:", err);
      showTooltip(err.message, true);
    }
  };

  const stakeDINTokens = async () => {
    try {
      const response = await fetch("http://localhost:8000/auditors/stakeDINTokens", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Fetched auditors state:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchAuditorsState();
      }, 1000);
    } catch (err) {
      console.error("Error fetching auditors state:", err);
      showTooltip(err.message, true);
    }
  };

  const stakeDINTokensSingle = async (address) => {
    try {
      const response = await fetch("http://localhost:8000/auditors/stakeDINTokensSingle", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          auditor_address: address,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("DIN Token Stake done successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchAuditorsState();
      }, 1000);

    } catch (err) {
      console.error("Error staking DIN Tokens:", err);
      showTooltip(err.message, true);
    }
  };

  const buyDINTokensSingle = async (address) => {
    try {
      console.log("Buy DIN Tokens for validator:", address);
      const response = await fetch("http://localhost:8000/auditors/buyDINTokensSingle", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          auditor_address: address,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Buy DIN Tokens done successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchAuditorsState();
      }, 1000);

    } catch (err) {
      console.error("Error buying DIN Tokens:", err);
      showTooltip(err.message, true);
    }
  };


  const registerTaskAuditors = async () => {
    try {
      const response = await fetch("http://localhost:8000/auditors/registerTaskAuditors", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Task Auditors registered successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchAuditorsState();
      }, 1000);

    } catch (err) {
      console.error("Error registering task auditors:", err);
      showTooltip(err.message, true);
    }
  };

  const registerTaskAuditorSingle = async (address) => {
    try {
      console.log("Register Task Auditor for auditor:", address);
      const response = await fetch("http://localhost:8000/auditors/registerTaskAuditorSingle", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          auditor_address: address,
        }),
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Register Task Auditor done successfully:", data);

      setLoading(false);
      showTooltip(data.message, false);
      setTimeout(() => {
        fetchAuditorsState();
      }, 1000);

    } catch (err) {
      console.error("Error registering task auditor:", err);
      showTooltip(err.message, true);
    }
  };

  const fetchAuditorEvaluationBatches = async () => {
    try {
      const response = await fetch("http://localhost:8000/auditors/getAuditorEvaluationBatches");
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      setAuditorEvaluationBatches(data.auditorEvaluationBatches);
      console.log("Fetched auditor evaluation batches successfully:", data);
      
    } catch (error) {
      console.error("Error fetching auditor evaluation batches:", error);
    }
  };  


  useEffect(() => {
    if (GIstate >= 13) {
      fetchAuditorEvaluationBatches()
    }
    
  }, [GIstate]);

  return (  
    <div className="tab-content">
      <h2>Auditors</h2>
      {loading ? (
        <div>Loading...</div>
      ) : (
        <>
        <div>
            <div>
            <h3>Total Registered Auditors</h3>
            <p>{registeredTaskAuditors.length} Auditors</p>
            </div>
            <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "1rem" }}>

              {dintoken_address ? (
                <button className="button button--primary" onClick={() => buyDINTokens()}>Buy DIN Tokens</button>
              ) : (
                <p> DIN Token Contract not deployed</p>
              )}
              {DINValidatorStakeAddress ? (
                <>
                <button className="button button--primary" onClick={() => stakeDINTokens()}>Stake DIN Tokens</button>
                </>
              ) : (
                <p> DIN Validator Stake Contract not deployed</p>
              )}

              {GIstatestr ==="DINauditorRegistrationStarted" ? (
                <button className="button button--primary" onClick={() => registerTaskAuditors()}>Register Task Auditors </button>
              ) : null}
            
            </div>  





        </div>
        {auditorAddresses.length > 0 ? (
          auditorAddresses.map((address, index) => (

            <div key={index} className="listbox">
              <h3>Address - {address} </h3><br/>
              <p>ETH Balance - {auditorETHBalances[index]} </p><br/> 

              {dintoken_address ? (
                <>  
                <p>DIN Token Balance - {AuditorsDintokenBalances[index]}</p> <br/> 
                </>
              ) : (
                <p>DIN Token Contract not deployed</p>
              )}

              <br/>
              {DINValidatorStakeAddress ? (
                <p>Staked DIN Tokens - {AuditorsDinStakedTokens[index]}</p>
              ) : (
                <p>DIN Validator Stake Contract not deployed</p>
              )}

              { (GIstate >=8)  && GI>0  && registeredTaskAuditors.length > 0 && registeredTaskAuditors.includes(address) ? ( // DINauditorRegistrationStarted
                <p><span style={{ color: 'green' }}>✅</span> Registered Auditor</p>
              ) : (
                <p><span style={{ color: 'red' }}>❌</span> Not Registered Auditor</p>
              )}

              {DINValidatorStakeAddress ? (
                <>
                <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "1rem" }}>
                <button className="button button--primary" onClick={() => buyDINTokensSingle(address)} >Buy DIN Tokens</button>
                </div>
                </>
              ): null
              }

              {DINValidatorStakeAddress ? (
                <>
                <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "1rem" }}>
                <button className="button button--primary" onClick={() => stakeDINTokensSingle(address)} >Stake DIN Tokens</button>
                </div>
                </>
              ): null
              }

              { (GIstate >= 8) && GI>0  && (registeredTaskAuditors.length > 0 || AuditorsDinStakedTokens[index] >= 1000000) && registeredTaskAuditors.indexOf(address) === -1 ? ( //DINauditorRegistrationStarted
                <>
                <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "1rem" }}>
                <button className="button button--primary" onClick={() =>registerTaskAuditorSingle(address)} >Register Task Auditor</button>
                </div>
                </>
              ) : null
              }

              {GIstate >= 13 && (
                <AuditorTaskCard
                key={address}
                auditorData={auditorEvaluationBatches[address] || { auditor: address, assignedModels: [] }}

                fetchAuditorEvaluationBatches={fetchAuditorEvaluationBatches}
              />
                )}

            </div>
          ))
        ) : (
          <div>No auditors available.</div>
        )}
        </>
      )}
    </div>
  );
}