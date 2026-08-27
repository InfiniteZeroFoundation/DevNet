import hre, { ethers } from "hardhat";

import {
  deployTransparentProxy,
  getProxyAdminAddress,
  savePlatformAddresses,
} from "../deploy/helpers";

async function main() {
  const [deployer] = await ethers.getSigners();

  console.log("Network:", hre.network.name);
  console.log("Deployer:", deployer.address);

  const DinToken = await ethers.getContractFactory("DinToken");
  const dinToken = await deployTransparentProxy(DinToken, []);
  const dinTokenAddress = await dinToken.getAddress();
  console.log("DinToken:", dinTokenAddress);

  const DinCoordinator = await ethers.getContractFactory("DinCoordinator");
  const dinCoordinator = await deployTransparentProxy(DinCoordinator, [
    dinTokenAddress,
  ]);
  const dinCoordinatorAddress = await dinCoordinator.getAddress();
  console.log("DinCoordinator:", dinCoordinatorAddress);

  await (await dinToken.setCoordinator(dinCoordinatorAddress)).wait();
  console.log("DinToken coordinator wired");

  const DinValidatorStake = await ethers.getContractFactory("DinValidatorStake");
  const dinValidatorStake = await deployTransparentProxy(DinValidatorStake, [
    dinTokenAddress,
    dinCoordinatorAddress,
  ]);
  const dinValidatorStakeAddress = await dinValidatorStake.getAddress();
  console.log("DinValidatorStake:", dinValidatorStakeAddress);

  await (
    await dinCoordinator.updateValidatorStakeContract(dinValidatorStakeAddress)
  ).wait();
  console.log("DinCoordinator stake contract wired");

  const DINModelRegistry = await ethers.getContractFactory("DINModelRegistry");
  const dinModelRegistry = await deployTransparentProxy(DINModelRegistry, [
    dinValidatorStakeAddress,
  ]);
  const dinModelRegistryAddress = await dinModelRegistry.getAddress();
  console.log("DINModelRegistry:", dinModelRegistryAddress);

  const proxyAdminToken       = await getProxyAdminAddress(dinTokenAddress);
  const proxyAdminCoordinator = await getProxyAdminAddress(dinCoordinatorAddress);
  const proxyAdminStake       = await getProxyAdminAddress(dinValidatorStakeAddress);
  const proxyAdminRegistry    = await getProxyAdminAddress(dinModelRegistryAddress);

  savePlatformAddresses(hre.network.name, {
    dinToken: dinTokenAddress,
    dinCoordinator: dinCoordinatorAddress,
    dinValidatorStake: dinValidatorStakeAddress,
    dinModelRegistry: dinModelRegistryAddress,
    proxyAdminToken,
    proxyAdminCoordinator,
    proxyAdminStake,
    proxyAdminRegistry,
  });

  console.log(`Saved deployments/${hre.network.name}.json`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
