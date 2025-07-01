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
function ModelOwnerTab({ setGIstate, fetchGIState, GIstate }) {
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
  const [clientModels, setClientModels] = useState([]);
  const [clientAddresses, setClientAddresses] = useState([]);
  

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
    } catch (err) {
      console.error("Error closing LM submissions:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }
  
  useEffect(() => {
    fetchModelOwnerState();
  }, []);


  const fetchClientModels = async () => {
    try {
      setLoading(true);
      const response = await fetch("http://localhost:8000/modelowner/getClientModels", {
        method: "POST",
      });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log(data);
      setClientModels(data.client_models);
      setClientAddresses(data.client_addresses);
    } catch (err) {
      console.error("Error fetching client models:", err);
      showTooltip(err.message, true);
    } finally {
      setLoading(false);
    }
  }

  const approveClientModel = async (clientAddress) => {

  }

  const rejectClientModel = async (clientAddress) => {

  }

  useEffect(() => {
    if (GIstate === "LM submissions closed" && clientModelsCreatedF){
      fetchClientModels();
    }
  }, [GIstate, clientModelsCreatedF]);

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
                {GIstate === "Genesis Model Created" || GIstate === "GI ended" ? (
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

                {GIstate === "GI started" && registeredTaskValidators.length >=12? (
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

                { GIstate === "LM submissions started" && clientModelsCreatedF ? (
                  <>
                  <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }}>
                  <button className="button button--primary" onClick={closeLMsubmissions}>
                  Close LM submissions
                  </button>
                </div>
                  </>
                ):null}

                {GIstate === "LM submissions closed" && clientModelsCreatedF ? (
                  <>
                  <div>
                    <h3>Client Models</h3>
                    {clientModels.map((model, index) => (
                      <div style={{ marginTop: "1rem", marginBottom: "1rem", display: "flex", justifyContent: "center" }} key={index} className="listbox">
                        <p>{clientAddresses[index]} : {model}</p>
                        <button 
                          className="button button--primary"
                          onClick={() => approveClientModel(clientAddresses[index])}
                        >
                          Approve Client Model
                        </button>

                        <button 
                          className="button button--danger"
                          onClick={() => rejectClientModel(clientAddresses[index])}
                        >
                          Reject Client Model
                        </button>
                      </div>
                    ))}
                  </div>
                  </>
                ):null}
                
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
function ClientsTab({setGIstate, fetchGIState, GIstate}) {

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

        {!clientModelsCreatedF && GIstate === "LM submissions started"? (
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
function ValidatorsTab({GIstate, GI}) {

  const [loading, setLoading] = useState(true);
  const { showTooltip } = useContext(TooltipContext);
  const [validatorAddresses, setValidatorAddresses] = useState([]);
  const [validatorDintokenBalances, setValidatorDintokenBalances] = useState([]);
  const [validatorETHBalances, setValidatorETHBalances] = useState([]);
  const [DINValidatorStakeAddress, setDINValidatorStakeAddress] = useState(null);
  const [validatorDinStakedTokens, setValidatorDinStakedTokens] = useState([]);
  const [dintoken_address, setDintokenAddress] = useState(null);
  const [registeredTaskValidators, setRegisteredTaskValidators] = useState([]);


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
            {GIstate === "GI started" ? (
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

              { (GIstate === "GI started" || GIstate === "LM submissions started" || GIstate === "LM submissions closed") && GI>0  && registeredTaskValidators.length > 0 &&registeredTaskValidators.includes(address) ? (
                <p><span style={{ color: 'green' }}>✅</span> Registered Validator</p>
              ) : (
                <p><span style={{ color: 'red' }}>❌</span> Not Registered Validator</p>
              )}
              

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

              { (GIstate === "GI started") && GI>0  && (registeredTaskValidators.length > 0 || validatorDinStakedTokens[index] >= 1000000) &&registeredTaskValidators.indexOf(address) === -1 ? (
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
  const [GIstate, setGIstate] = useState("started");
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
              <h3>Global Iteration State: {GIstate}</h3>
            </div>
            </>
          )}
            
          <TabBar activeTab={activeTab} setActiveTab={setActiveTab} />
          {activeTab === "DINDAO" && <DINDAO />}
          {activeTab === "ModelOwner" && <ModelOwnerTab setGIstate={setGIstate} fetchGIState={fetchGIState} GIstate={GIstate}/>}
          {activeTab === "Validators" && <ValidatorsTab GIstate={GIstate} GI={GI}/>}
          {activeTab === "Clients" && <ClientsTab setGIstate={setGIstate} fetchGIState={fetchGIState} GIstate={GIstate}/>}
        </div>
      </main>

      <footer className="footer">
        <p>&copy; 2025 DIN MVP</p>
      </footer>
    </div>
  );
}

export default App;
