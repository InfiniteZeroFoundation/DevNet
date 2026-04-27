import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import * as dotenv from "dotenv";
import * as fs from "fs";
import "hardhat-contract-sizer";
import * as path from "path";
import { task } from "hardhat/config";
import { HardhatRuntimeEnvironment } from "hardhat/types";

// Load base .env
dotenv.config({ path: "../.env" });

// Load network-specific .env
const network = process.env.NETWORK || "local";
const sepolia_op_devnet_rpc_url = process.env.SEPOLIA_OP_DEVNET_RPC_URL;
const envFile = `../.env.${network}`;

if (fs.existsSync(envFile)) {
  dotenv.config({ path: envFile });
  console.log(`Loaded ${envFile}`);
} else {
  console.log(`Warning: ${envFile} not found`);
}


const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.28",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200
      },
      viaIR: true,
      // ✅ CRITICAL: Set EVM version to Cancun for TSTORE/TLOAD support
      evmVersion: "cancun"
    }
  },
  networks: {
    hardhat: {
      hardfork: "cancun",    // ✅ Required for local testing
      ...(process.env.ALCHEMY_API_KEY
        ? {
          forking: {
            url: `https://eth-mainnet.g.alchemy.com/v2/${process.env.ALCHEMY_API_KEY}`,
            // Replace with your Alchemy API key
            //blockNumber: 18700000, // Optional: specific block to fork from (or remove to fork latest)
          },
        }
        : {}),
      accounts: {
        count: 70, // Generate 70 accounts
        accountsBalance: "10000000000000000000000"
      },
      chainId: 1337,
      allowUnlimitedContractSize: true,
    },
    sepolia_op_devnet: {
      url: sepolia_op_devnet_rpc_url,
      accounts: [process.env.ETH_PRIVATE_KEY_0!, process.env.ETH_PRIVATE_KEY_1!],
      chainId: 11155420,
    },

    localhost: {
      url: "http://127.0.0.1:8545",
    },
  },
  etherscan: {
    apiKey: {
      sepolia_op_devnet: process.env.ETHERSCAN_API_KEY!,
    },
    customChains: [
      {
        network: "sepolia_op_devnet",
        chainId: 11155420,
        urls: {
          apiURL: "https://api.etherscan.io/v2/api?chainid=11155420",
          browserURL: "https://sepolia-optimism.etherscan.io",
        }
      }
    ]
  },
  sourcify: {
    enabled: false
  },
  mocha: {
    timeout: 100000000 // Set a very high timeout for tests
  }
};

export default config;
