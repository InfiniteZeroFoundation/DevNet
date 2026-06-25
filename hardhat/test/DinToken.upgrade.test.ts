import { expect } from "chai";
import { ethers, upgrades } from "hardhat";

import { PROXY_KIND } from "../deploy/constants";
import { upgradeTransparentProxy } from "../deploy/helpers";
import { deployPlatform, mintDinViaDeposit } from "./helpers/platform";

describe("DinToken upgrade", function () {
  it("preserves balances and coordinator wiring across upgrade", async function () {
    const { deployer, user, dinToken, dinCoordinator } = await deployPlatform();
    const proxyAddress = await dinToken.getAddress();
    const coordinatorAddress = await dinCoordinator.getAddress();

    await mintDinViaDeposit(dinCoordinator, user, 10_000_000_000_000_000n);
    const balanceBefore = await dinToken.balanceOf(user.address);

    const DinTokenV2 = await ethers.getContractFactory("DinTokenV2");
    await upgrades.validateUpgrade(proxyAddress, DinTokenV2, {
      kind: PROXY_KIND,
    });
    const upgraded = await upgradeTransparentProxy(proxyAddress, DinTokenV2);

    expect(await upgraded.coordinator()).to.equal(coordinatorAddress);
    expect(await upgraded.balanceOf(user.address)).to.equal(balanceBefore);
    expect(await upgraded.version()).to.equal(2);

    await mintDinViaDeposit(dinCoordinator, user, 1_000_000_000_000_000n);
    expect(await upgraded.balanceOf(user.address)).to.be.gt(balanceBefore);
  });

  it("keeps mint restricted to coordinator after upgrade", async function () {
    const { user, dinToken } = await deployPlatform();
    const proxyAddress = await dinToken.getAddress();

    const DinTokenV2 = await ethers.getContractFactory("DinTokenV2");
    await upgradeTransparentProxy(proxyAddress, DinTokenV2);

    await expect(
      dinToken.connect(user).mint(user.address, 1)
    ).to.be.revertedWithCustomError(dinToken, "Unauthorized");
  });

  it("keeps coordinator setup restricted to owner after upgrade", async function () {
    const { other, dinToken, dinCoordinator } = await deployPlatform();
    const proxyAddress = await dinToken.getAddress();

    const DinTokenV2 = await ethers.getContractFactory("DinTokenV2");
    await upgradeTransparentProxy(proxyAddress, DinTokenV2);

    await expect(
      dinToken.connect(other).setCoordinator(await dinCoordinator.getAddress())
    ).to.be.revertedWithCustomError(dinToken, "OwnableUnauthorizedAccount");
  });
});
