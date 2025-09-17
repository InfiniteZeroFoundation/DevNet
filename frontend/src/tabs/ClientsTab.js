import React, { useState, useEffect, useContext, useCallback } from "react";
import { TooltipContext } from "../context/TooltipContext";


export default function ClientsTab({ GIstate, GI}) {

  const { showTooltip } = useContext(TooltipContext);

  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const [clientModelsCreatedF, setClientModelsCreatedF] = useState(false);
  const [client_model_ipfs_hashes, setClientModelIpfsHashes] = useState([]);
  const [clients_address, setClientsAddress] = useState([]);
  
  // differential privacy state 
  // Possible values: "afterTraining", "disabled"
  //"beforeTraining" is not supported for now
  const [dpModeUsed, setDpModeUsed] = useState("afterTraining"); 

  // Differential Privacy selection before creation
  const [selectedDPMode, setSelectedDPMode] = useState("afterTraining");

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
        console.log("Fetched client model state:", data);
        setClientModelsCreatedF(data.client_models_created_f);
        setClientModelIpfsHashes(data.client_model_ipfs_hashes);
        setClientsAddress(data.client_addresses);
        // If the backend returns the DP mode used, show it
        if (data.dp_mode) {
          setDpModeUsed(data.dp_mode);
        }
        setLoading(false);
      } catch (err) {
        console.error("Error fetching clientModelsCreatedF state:", err);
        showTooltip(err.message, true);
      } finally {
        setLoading(false);
      }
    };

    fetchClientModelState();
  }, []);

  const createClientModels = useCallback(async () => {
    try {
      setCreating(true);
      console.log("Selected DP Mode:", selectedDPMode);
      const response = await fetch("http://localhost:8000/clients/createClientModels", { 
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          selectedDPMode: selectedDPMode,
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log("Created client models:", data);
      
      // Show tooltip
      if (data.status === "success") {
        setClientModelsCreatedF(data.client_models_created_f);
        setClientsAddress(data.client_addresses);
        setClientModelIpfsHashes(data.client_model_ipfs_hashes);
        if (data.dp_mode) {
          setDpModeUsed(data.dp_mode);
        }
        showTooltip(data.message, false);
      } else {
        showTooltip(data.message, true);
      }
    } catch (err) {
      console.error("Error creating client models:", err);
      // Show error tooltip
      showTooltip(err.message, true);
    } finally {
      setCreating(false);
    }
  }, [selectedDPMode]);

  const canCreateModels = !clientModelsCreatedF && GIstate === 10; //LMSstarted
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
          <label htmlFor="DPMode">Differential Privacy Mode: </label>
          <select
            id="DPMode"
            value={selectedDPMode}
            onChange={(e) => setSelectedDPMode(e.target.value)}
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
            <p>{dpModeUsed}</p>

            <h3>Client Models Available</h3>
          {clients_address.length > 0 ? (
            clients_address.map((address, index) => (
              <p key={address}>
                {address} : {client_model_ipfs_hashes[index]}
              </p>
            ))
          ): (<p>No clients found.</p>)
          }
          </div>

        )}

        {canCreateModels? (
          <div>
          <h3>Client Models Not Available</h3>
          <button className="button button--primary" onClick={() => createClientModels()} disabled={creating} style={{ marginTop: "1rem" }}>{creating ? "Creating..." : "Create Client Models"}</button>
        </div>
        ):null}
        </> 
      )}
    </div>
  );
}