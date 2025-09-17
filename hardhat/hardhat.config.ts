import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";

const config: HardhatUserConfig = {
  solidity: "0.8.28",
  networks: {
    hardhat: {
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
