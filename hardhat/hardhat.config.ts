import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import * as dotenv from "dotenv";
import * as fs from "fs";

// Load base .env
dotenv.config({ path: "../.env" });

// Load network-specific .env
const network = process.env.NETWORK || "local";
const envFile = `../.env.${network}`;

if (fs.existsSync(envFile)) {
  dotenv.config({ path: envFile });
  console.log(`Loaded ${envFile}`);
} else {
  console.log(`Warning: ${envFile} not found`);
}


const config: HardhatUserConfig = {
  solidity: "0.8.28",
  networks: {
    hardhat: {
      forking: {
        url: `https://eth-mainnet.g.alchemy.com/v2/${process.env.ALCHEMY_API_KEY}`, // Replace with your Alchemy API key
        //blockNumber: 18700000, // Optional: specific block to fork from (or remove to fork latest)
      },
      accounts: {
        count: 70, // Generate 70 accounts
        accountsBalance: "10000000000000000000000"
      },
      chainId: 1337,
      allowUnlimitedContractSize: true,
    },
    localhost: {
      url: "http://127.0.0.1:8545",
    },
  },
  mocha: {
    timeout: 100000000 // Set a very high timeout for tests
  }
};

export default config;
