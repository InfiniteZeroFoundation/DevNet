import { expect } from "chai";
import { ethers, upgrades } from "hardhat";

import { PROXY_KIND } from "../deploy/constants";
import { upgradeTransparentProxy } from "../deploy/helpers";
import { deployPlatform, mintDinViaDeposit } from "./helpers/platform";

const MIN_STAKE = 10n * 10n ** 18n;
const STAKE_DEPOSIT_ETH = 10_000_000_000_000_000n;

describe("DinValidatorStake upgrade", function () {
  it("preserves stake balances across upgrade", async function () {
    const { user, dinToken, dinCoordinator, dinValidatorStake } =
      await deployPlatform();
    const proxyAddress = await dinValidatorStake.getAddress();

    await mintDinViaDeposit(dinCoordinator, user, STAKE_DEPOSIT_ETH);
    await dinToken
      .connect(user)
      .approve(proxyAddress, MIN_STAKE);
    await dinValidatorStake.connect(user).stake(MIN_STAKE);

    const stakeBefore = await dinValidatorStake.getStake(user.address);

    const DinValidatorStakeV2 = await ethers.getContractFactory(
      "DinValidatorStakeV2"
    );
    await upgrades.validateUpgrade(proxyAddress, DinValidatorStakeV2, {
      kind: PROXY_KIND,
    });
    const upgraded = await upgradeTransparentProxy(
      proxyAddress,
      DinValidatorStakeV2
    );

    expect(await upgraded.getStake(user.address)).to.equal(stakeBefore);
    expect(await upgraded.isValidatorActive(user.address)).to.equal(true);
    expect(await upgraded.version()).to.equal(2);
  });

  it("keeps slasher registration restricted to coordinator after upgrade", async function () {
    const { deployer, other, dinValidatorStake } = await deployPlatform();
    const proxyAddress = await dinValidatorStake.getAddress();

    const MockSlasher = await ethers.getContractFactory("MockSlasher");
    const slasher = await MockSlasher.deploy(deployer.address);
    await slasher.waitForDeployment();
    const slasherAddress = await slasher.getAddress();

    const DinValidatorStakeV2 = await ethers.getContractFactory(
      "DinValidatorStakeV2"
    );
    await upgradeTransparentProxy(proxyAddress, DinValidatorStakeV2);

    await expect(
      dinValidatorStake.connect(other).addSlasherContract(slasherAddress)
    ).to.be.revertedWithCustomError(dinValidatorStake, "NotDINCoordinator");
  });

  it("keeps blacklist control with owner after upgrade", async function () {
    const { deployer, other, user, dinToken, dinCoordinator, dinValidatorStake } =
      await deployPlatform();
    const proxyAddress = await dinValidatorStake.getAddress();

    await mintDinViaDeposit(dinCoordinator, user, STAKE_DEPOSIT_ETH);
    await dinToken.connect(user).approve(proxyAddress, MIN_STAKE);
    await dinValidatorStake.connect(user).stake(MIN_STAKE);

    const DinValidatorStakeV2 = await ethers.getContractFactory(
      "DinValidatorStakeV2"
    );
    await upgradeTransparentProxy(proxyAddress, DinValidatorStakeV2);

    await dinValidatorStake.connect(deployer).blacklistValidator(user.address);
    expect(await dinValidatorStake.isValidatorActive(user.address)).to.equal(
      false
    );

    await expect(
      dinValidatorStake.connect(other).unblacklistValidator(user.address)
    ).to.be.revertedWithCustomError(
      dinValidatorStake,
      "OwnableUnauthorizedAccount"
    );
  });
});
