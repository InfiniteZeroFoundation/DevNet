import { expect } from "chai";
import { ethers, upgrades } from "hardhat";

import { PROXY_KIND } from "../deploy/constants";
import { upgradeTransparentProxy } from "../deploy/helpers";
import { deployPlatform, mintDinViaDeposit } from "./helpers/platform";

describe("DinCoordinator upgrade", function () {
  it("preserves exchange rate and token wiring across upgrade", async function () {
    const { user, dinToken, dinCoordinator } = await deployPlatform();
    const proxyAddress = await dinCoordinator.getAddress();
    const tokenAddress = await dinToken.getAddress();
    const newRate = 2_000_000n * 10n ** 18n;

    await dinCoordinator.updateDinPerEth(newRate);
    await mintDinViaDeposit(dinCoordinator, user, 10_000_000_000_000_000n);
    const balanceBefore = await dinToken.balanceOf(user.address);

    const DinCoordinatorV2 = await ethers.getContractFactory("DinCoordinatorV2");
    await upgrades.validateUpgrade(proxyAddress, DinCoordinatorV2, {
      kind: PROXY_KIND,
    });
    const upgraded = await upgradeTransparentProxy(
      proxyAddress,
      DinCoordinatorV2
    );

    expect(await upgraded.dinToken()).to.equal(tokenAddress);
    expect(await upgraded.dinPerEth()).to.equal(newRate);
    expect(await upgraded.version()).to.equal(2);
    expect(await dinToken.balanceOf(user.address)).to.equal(balanceBefore);
  });

  it("keeps owner-only functions restricted after upgrade", async function () {
    const { other, dinCoordinator } = await deployPlatform();
    const proxyAddress = await dinCoordinator.getAddress();

    const DinCoordinatorV2 = await ethers.getContractFactory("DinCoordinatorV2");
    await upgradeTransparentProxy(proxyAddress, DinCoordinatorV2);

    await expect(
      dinCoordinator.connect(other).updateDinPerEth(1)
    ).to.be.revertedWithCustomError(
      dinCoordinator,
      "OwnableUnauthorizedAccount"
    );
  });

  it("keeps slasher management wired to stake contract after upgrade", async function () {
    const { deployer, dinCoordinator, dinValidatorStake } =
      await deployPlatform();
    const proxyAddress = await dinCoordinator.getAddress();

    const MockSlasher = await ethers.getContractFactory("MockSlasher");
    const slasher = await MockSlasher.deploy(deployer.address);
    await slasher.waitForDeployment();

    await dinCoordinator.addSlasherContract(await slasher.getAddress());
    expect(
      await dinValidatorStake.isSlasherContract(await slasher.getAddress())
    ).to.equal(true);

    const DinCoordinatorV2 = await ethers.getContractFactory("DinCoordinatorV2");
    await upgradeTransparentProxy(proxyAddress, DinCoordinatorV2);

    expect(
      await dinValidatorStake.isSlasherContract(await slasher.getAddress())
    ).to.equal(true);
  });

  it("implementation contract cannot be initialized directly", async function () {
    const DinCoordinator = await ethers.getContractFactory("DinCoordinator");
    const impl = await DinCoordinator.deploy();
    await impl.waitForDeployment();
    const [signer] = await ethers.getSigners();
    await expect(impl.initialize(signer.address)).to.be.revertedWithCustomError(
      impl,
      "InvalidInitialization"
    );
  });
});
