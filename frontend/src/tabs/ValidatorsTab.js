
import React, { useState, useEffect, useContext } from "react";
import { TooltipContext } from "../context/TooltipContext";

/** ======================= Validator TAB ======================= */
export default function ValidatorsTab({GIstate, GI, GIstatestr}) {

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

      if (GIstate >= 15 && GI > 0) { // T1AggregationStarted
        setAllRegValT1Bs(data.all_reg_val_assigned_t1_batches)
        setAllRegValT2Bs(data.all_reg_val_assigned_t2_batches)
        setAllRegValT1BR(data.all_res_val_t1)
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
      console.log("Buy DIN tokens:", data);

      setLoading(false);
      setValidatorAddresses(data.validator_addresses);
      setValidatorDintokenBalances(data.validator_dintoken_balances);
      setValidatorETHBalances(data.validator_eth_balances);
    } catch (err) {
      console.error("Error buying DIN tokens:", err);
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
      console.log("Validator submit Aggregate Maliciously T1 status:", data);

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
    const cids = all_reg_val_t1br[validatorIndex];

    let curr_cid = null;
    
    console.log("validator_address: ", address);
    console.log("cids: ", cids);
    if (cids.length > 0) {
      for (let i = 0; i < cids.length; i++) {
        if (cids[i] !== null) {
          curr_cid = cids[i];
          break;
        }
      }
    }
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
        {GIstatestr === "T1AggregationStarted" && batches.length > 0 && !curr_cid? (
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
          )  : GIstate >= 16 && batches.length > 0 && curr_cid ? ( // T1AggregationStarted
            // Show submitted CID otherwise if conditions match
            <div>
              <h3>Submitted CID: {curr_cid}</h3>
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

    console.log("all_reg_val_t2br: ", all_reg_val_t2br);
  
    // 2. Get the assigned Tier-2 batches
    const batches = all_reg_val_t2bs[validatorIndex];
    const cids = all_reg_val_t2br[validatorIndex];

    let curr_cid = null;
    
    console.log("validator_address t2: ", address);
    console.log("cids t2: ", cids);
    if (cids === null) {
      cids = [];
    }
    if (cids.length > 0) {
      for (let i = 0; i < cids.length; i++) {
        if (cids[i] !== null) {
          curr_cid = cids[i];
          break;
        }
      }
    }
  
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
        {GIstatestr === "T2AggregationStarted" && batches.length > 0 && !curr_cid? (  //T2AggregationStarted
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
          ) : GIstate >= 17 && batches.length > 0 && curr_cid ? ( //T2AggregationStarted
            // Show submitted CID otherwise if conditions match
            <div>
              <h3>Submitted CID: {curr_cid}</h3>
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
            {GIstatestr ==="DINvalidatorRegistrationStarted" ? (
              <button className="button button--primary" onClick={() => registerTaskValidators()}>Register Task Validators </button>
            ) : null}
          </div>  
          {validatorAddresses.length > 0 ? (
           validatorAddresses.map((address, index) => (
            <div key={index} className="listbox">
              <h3>Address - {address} </h3><br/> 
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

              { (GIstate >=6)  && GI>0  && registeredTaskValidators.length > 0 && registeredTaskValidators.includes(address) ? ( // DINvalidatorRegistrationStarted
                <p><span style={{ color: 'green' }}>✅</span> Registered Validator</p>
              ) : (
                <p><span style={{ color: 'red' }}>❌</span> Not Registered Validator</p>
              )}

              {(GIstate >=14)  && GI>0  && registeredTaskValidators.length > 0 && registeredTaskValidators.includes(address) ? ( // T1nT2Bcreated
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

              { (GIstate >= 6) && GI>0  && (registeredTaskValidators.length > 0 || validatorDinStakedTokens[index] >= 1000000) && registeredTaskValidators.indexOf(address) === -1 ? ( //DINvalidatorRegistrationStarted
                <>
                <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "1rem" }}>
                <button className="button button--primary" onClick={() =>registerTaskValidatorSingle(address)} >Register Task Validator</button>
                </div>
                </>
              ) : null
              }
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
