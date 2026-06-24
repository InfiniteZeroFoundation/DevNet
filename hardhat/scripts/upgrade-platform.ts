import hre, { ethers, upgrades } from "hardhat";

import { PLATFORM_CONTRACTS } from "../deploy/constants";
import {
  loadPlatformAddresses,
  upgradeTransparentProxy,
} from "../deploy/helpers";
import type { PlatformAddresses } from "../deploy/types";

const PROXY_KEYS: Record<
  (typeof PLATFORM_CONTRACTS)[number],
  keyof PlatformAddresses
> = {
  DinToken: "dinToken",
  DinCoordinator: "dinCoordinator",
  DinValidatorStake: "dinValidatorStake",
  DINModelRegistry: "dinModelRegistry",
};

async function main() {
  const contractName = process.env.CONTRACT;
  if (!contractName) {
    throw new Error(
      `Set CONTRACT to one of: ${PLATFORM_CONTRACTS.join(", ")}`
    );
  }

  if (
    !PLATFORM_CONTRACTS.includes(
      contractName as (typeof PLATFORM_CONTRACTS)[number]
    )
  ) {
    throw new Error(
      `Unknown CONTRACT "${contractName}". Expected one of: ${PLATFORM_CONTRACTS.join(", ")}`
    );
  }

  const addresses = loadPlatformAddresses(hre.network.name);
  const proxyKey =
    PROXY_KEYS[contractName as (typeof PLATFORM_CONTRACTS)[number]];
  const proxyAddress = addresses[proxyKey];
  if (!proxyAddress) {
    throw new Error(`No proxy address for ${contractName} in deployment file`);
  }

  console.log("Network:", hre.network.name);
  console.log("Upgrading:", contractName);
  console.log("Proxy:", proxyAddress);

  const factory = await ethers.getContractFactory(contractName);
  await upgradeTransparentProxy(proxyAddress, factory);

  const implementationAddress =
    await upgrades.erc1967.getImplementationAddress(proxyAddress);

  console.log("Proxy:", proxyAddress);
  console.log("Implementation:", implementationAddress);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
