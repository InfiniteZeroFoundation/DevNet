import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import * as dotenv from "dotenv";
import * as fs from "fs";
import "hardhat-contract-sizer";
import * as path from "path";
import { task } from "hardhat/config";
import { HardhatRuntimeEnvironment } from "hardhat/types";


// ✅ Import from ethers v6
import { Wallet, HDNodeWallet } from "ethers";

interface DevAccount {
  address: string;
  private_key: string;
}

task("export-accounts", "Exports Hardhat default accounts")
  .addParam("output", "Output JSON file path", "./accounts.json")
  .setAction(async ({ output }: { output: string }, hre: HardhatRuntimeEnvironment) => {
    const accounts: DevAccount[] = [];
    const count = 70;
    const MNEMONIC = "test test test test test test test test test test test junk";

    // You no longer need a 'baseNode' variable defined outside the loop if using Option B

    for (let i = 0; i < count; i++) {
      // Define the FULL absolute path for the specific child account
      const pathStr = `m/44'/60'/0'/0/${i}`;

      // ✅ Use HDNodeWallet.fromPhrase with the full path in the third argument
      // This function internally handles generating the root node and then deriving the absolute path
      const wallet = HDNodeWallet.fromPhrase(MNEMONIC, undefined, pathStr);

      accounts.push({
        address: wallet.address,
        private_key: wallet.privateKey,
      });
      console.log(`Account #${i}: ${wallet.address} using path: ${pathStr}`);
    }


    const data = { hardhat: accounts };
    const outputPath = path.resolve(output);
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    fs.writeFileSync(outputPath, JSON.stringify(data, null, 2));

    console.log(`\n✅ Saved ${count} accounts to: ${outputPath}`);
  });

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
  solidity: {
    version: "0.8.28",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200
      },
      viaIR: true
    }
  },
  networks: {
    hardhat: {
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
    localhost: {
      url: "http://127.0.0.1:8545",
    },
  },
  mocha: {
    timeout: 100000000 // Set a very high timeout for tests
  }
};

export default config;
