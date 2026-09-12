import { Contract } from "ethers";
import { ethers } from "hardhat";

import { deployTransparentProxy } from "../../deploy/helpers";

export interface PlatformFixture {
  deployer: Awaited<ReturnType<typeof ethers.getSigners>>[0];
  user: Awaited<ReturnType<typeof ethers.getSigners>>[0];
  other: Awaited<ReturnType<typeof ethers.getSigners>>[0];
  dinToken: Contract;
  dinCoordinator: Contract;
  dinValidatorStake: Contract;
  dinModelRegistry: Contract;
}

export async function deployPlatform(): Promise<PlatformFixture> {
  const [deployer, user, other] = await ethers.getSigners();

  const DinToken = await ethers.getContractFactory("DinToken");
  const dinToken = await deployTransparentProxy(DinToken, []);
  const dinTokenAddress = await dinToken.getAddress();

  const DinCoordinator = await ethers.getContractFactory("DinCoordinator");
  const dinCoordinator = await deployTransparentProxy(DinCoordinator, [
    dinTokenAddress,
  ]);
  const dinCoordinatorAddress = await dinCoordinator.getAddress();

  await (await dinToken.setCoordinator(dinCoordinatorAddress)).wait();

  const DinValidatorStake = await ethers.getContractFactory("DinValidatorStake");
  const dinValidatorStake = await deployTransparentProxy(DinValidatorStake, [
    dinTokenAddress,
    dinCoordinatorAddress,
  ]);
  const dinValidatorStakeAddress = await dinValidatorStake.getAddress();

  await (
    await dinCoordinator.updateValidatorStakeContract(dinValidatorStakeAddress)
  ).wait();

  const DINModelRegistry = await ethers.getContractFactory("DINModelRegistry");
  const dinModelRegistry = await deployTransparentProxy(DINModelRegistry, [
    dinValidatorStakeAddress,
  ]);

  return {
    deployer,
    user,
    other,
    dinToken,
    dinCoordinator,
    dinValidatorStake,
    dinModelRegistry,
  };
}

export async function mintDinViaDeposit(
  dinCoordinator: Contract,
  user: Awaited<ReturnType<typeof ethers.getSigners>>[0],
  ethAmount: bigint
) {
  await dinCoordinator.connect(user).depositAndMint({ value: ethAmount });
}
