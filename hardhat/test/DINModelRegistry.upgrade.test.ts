import { expect } from "chai";
import { ethers, upgrades } from "hardhat";

import { PROXY_KIND } from "../deploy/constants";
import { upgradeTransparentProxy } from "../deploy/helpers";
import { deployPlatform } from "./helpers/platform";

describe("DINModelRegistry upgrade", function () {
  it("preserves fee settings and model state across upgrade", async function () {
    const { deployer, user, dinCoordinator, dinModelRegistry } =
      await deployPlatform();
    const proxyAddress = await dinModelRegistry.getAddress();

    const newProprietaryFee = 42n;
    await dinModelRegistry.connect(deployer).setProprietaryFee(newProprietaryFee);

    const MockSlasher = await ethers.getContractFactory("MockSlasher");
    const coordinatorSlasher = await MockSlasher.deploy(user.address);
    const auditorSlasher = await MockSlasher.deploy(user.address);
    await coordinatorSlasher.waitForDeployment();
    await auditorSlasher.waitForDeployment();

    const coordinatorSlasherAddress = await coordinatorSlasher.getAddress();
    const auditorSlasherAddress = await auditorSlasher.getAddress();

    await dinCoordinator.addSlasherContract(coordinatorSlasherAddress);
    await dinCoordinator.addSlasherContract(auditorSlasherAddress);

    const manifestCID = ethers.id("manifest-v1");
    const fee = await dinModelRegistry.proprietaryFee();
    await dinModelRegistry.connect(user).requestModelRegistration(
      manifestCID,
      coordinatorSlasherAddress,
      auditorSlasherAddress,
      false,
      { value: fee }
    );
    await dinModelRegistry.connect(deployer).approveModel(0);

    const DINModelRegistryV2 = await ethers.getContractFactory(
      "DINModelRegistryV2"
    );
    await upgrades.validateUpgrade(proxyAddress, DINModelRegistryV2, {
      kind: PROXY_KIND,
    });
    const upgraded = await upgradeTransparentProxy(
      proxyAddress,
      DINModelRegistryV2
    );

    expect(await upgraded.proprietaryFee()).to.equal(newProprietaryFee);
    expect(await upgraded.totalModels()).to.equal(1);
    expect(await upgraded.version()).to.equal(2);

    const model = await upgraded.getModel(0);
    expect(model.owner).to.equal(user.address);
    expect(model.manifestCID).to.equal(manifestCID);
    expect(model.taskCoordinator).to.equal(coordinatorSlasherAddress);
    expect(model.taskAuditor).to.equal(auditorSlasherAddress);
  });

  it("keeps owner-only governance restricted after upgrade", async function () {
    const { other, dinModelRegistry } = await deployPlatform();
    const proxyAddress = await dinModelRegistry.getAddress();

    const DINModelRegistryV2 = await ethers.getContractFactory(
      "DINModelRegistryV2"
    );
    await upgradeTransparentProxy(proxyAddress, DINModelRegistryV2);

    await expect(
      dinModelRegistry.connect(other).setProprietaryFee(1)
    ).to.be.revertedWithCustomError(
      dinModelRegistry,
      "OwnableUnauthorizedAccount"
    );
  });

  it("keeps pending requests readable after upgrade", async function () {
    const { deployer, user, dinCoordinator, dinModelRegistry } =
      await deployPlatform();
    const proxyAddress = await dinModelRegistry.getAddress();

    const MockSlasher = await ethers.getContractFactory("MockSlasher");
    const coordinatorSlasher = await MockSlasher.deploy(user.address);
    const auditorSlasher = await MockSlasher.deploy(user.address);
    await coordinatorSlasher.waitForDeployment();
    await auditorSlasher.waitForDeployment();

    await dinCoordinator.addSlasherContract(await coordinatorSlasher.getAddress());
    await dinCoordinator.addSlasherContract(await auditorSlasher.getAddress());

    const fee = await dinModelRegistry.openSourceFee();
    await dinModelRegistry.connect(user).requestModelRegistration(
      ethers.id("manifest-pending"),
      await coordinatorSlasher.getAddress(),
      await auditorSlasher.getAddress(),
      true,
      { value: fee }
    );

    const DINModelRegistryV2 = await ethers.getContractFactory(
      "DINModelRegistryV2"
    );
    await upgradeTransparentProxy(proxyAddress, DINModelRegistryV2);

    expect(await dinModelRegistry.totalModelRequests()).to.equal(1);

    const request = await dinModelRegistry.modelRequests(0);
    expect(request.requester).to.equal(user.address);
    expect(request.processed).to.equal(false);

    await dinModelRegistry.connect(deployer).approveModel(0);
    expect(await dinModelRegistry.totalModels()).to.equal(1);
  });
});
