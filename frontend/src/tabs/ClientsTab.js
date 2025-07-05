import React, { useState, useEffect, useContext } from "react";
import { TooltipContext } from "../context/TooltipContext";


/** ======================= Clients TAB ======================= */
export default function ClientsTab({ GIstate, GI}) {

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

        {!clientModelsCreatedF && GIstate === 3? (
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