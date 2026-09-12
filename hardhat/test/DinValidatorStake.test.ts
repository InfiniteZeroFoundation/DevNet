import { setBalance } from "@nomicfoundation/hardhat-network-helpers";
import { time } from "@nomicfoundation/hardhat-network-helpers";
import { expect } from "chai";
import { ethers } from "hardhat";

import { deployPlatform, mintDinViaDeposit } from "./helpers/platform";

const MIN_STAKE = 10n * 10n ** 18n;
const UNBONDING_PERIOD = 7 * 24 * 60 * 60; // 7 days in seconds
const STAKE_DEPOSIT_ETH = 10_000_000_000_000_000n; // 0.01 ETH → ~10,000 DIN at default rate

async function setup() {
  const platform = await deployPlatform();
  const { deployer, user, dinToken, dinCoordinator, dinValidatorStake } =
    platform;
  const stakeAddr = await dinValidatorStake.getAddress();

  const MockSlasher = await ethers.getContractFactory("MockSlasher");
  const mockSlasher = await MockSlasher.deploy(deployer.address);
  await mockSlasher.waitForDeployment();
  const slasherAddr = await mockSlasher.getAddress();
  await dinCoordinator.addSlasherContract(slasherAddr);

  await mintDinViaDeposit(dinCoordinator, user, STAKE_DEPOSIT_ETH);
  await dinToken.connect(user).approve(stakeAddr, ethers.MaxUint256);

  return { ...platform, slasherAddr, stakeAddr };
}

describe("DinValidatorStake", function () {
  describe("staking", function () {
    it("accepts MIN_STAKE and marks validator Active", async function () {
      const { user, dinValidatorStake } = await setup();
      await dinValidatorStake.connect(user).stake(MIN_STAKE);
      expect(await dinValidatorStake.getStake(user.address)).to.equal(MIN_STAKE);
      expect(await dinValidatorStake.isValidatorActive(user.address)).to.equal(
        true
      );
    });

    it("reverts when stake is below MIN_STAKE", async function () {
      const { user, dinValidatorStake } = await setup();
      await expect(
        dinValidatorStake.connect(user).stake(MIN_STAKE - 1n)
      ).to.be.revertedWithCustomError(
        dinValidatorStake,
        "AmountLessThanMinStake"
      );
    });

    it("reverts when validator is blacklisted", async function () {
      const { deployer, user, dinValidatorStake } = await setup();
      await dinValidatorStake.connect(deployer).blacklistValidator(user.address);
      await expect(
        dinValidatorStake.connect(user).stake(MIN_STAKE)
      ).to.be.revertedWithCustomError(dinValidatorStake, "ValidatorIsBlacklisted");
    });
  });

  describe("unstake and unbonding window", function () {
    it("moves stake to pending and sets withdrawAvailableAt", async function () {
      const { user, dinValidatorStake } = await setup();
      await dinValidatorStake.connect(user).stake(MIN_STAKE);
      await dinValidatorStake.connect(user).unstake(MIN_STAKE);

      const info = await dinValidatorStake.validators(user.address);
      expect(info.activeStake).to.equal(0n);
      expect(info.pendingWithdrawals).to.equal(MIN_STAKE);
      expect(info.withdrawAvailableAt).to.be.gt(0n);
    });

    it("reverts claimUnstaked before unbonding period elapses", async function () {
      const { user, dinValidatorStake } = await setup();
      await dinValidatorStake.connect(user).stake(MIN_STAKE);
      await dinValidatorStake.connect(user).unstake(MIN_STAKE);
      await expect(
        dinValidatorStake.connect(user).claimUnstaked()
      ).to.be.revertedWithCustomError(dinValidatorStake, "WithdrawalNotReady");
    });

    it("allows claimUnstaked after unbonding period and returns tokens", async function () {
      const { user, dinToken, dinValidatorStake } = await setup();
      await dinValidatorStake.connect(user).stake(MIN_STAKE);
      const balanceBefore = await dinToken.balanceOf(user.address);

      await dinValidatorStake.connect(user).unstake(MIN_STAKE);
      await time.increase(UNBONDING_PERIOD + 1);
      await dinValidatorStake.connect(user).claimUnstaked();

      expect(await dinToken.balanceOf(user.address)).to.equal(
        balanceBefore + MIN_STAKE
      );
      expect(await dinValidatorStake.getStake(user.address)).to.equal(0n);
    });

    it("reverts second unstake when a pending withdrawal exists", async function () {
      const { user, dinToken, dinCoordinator, dinValidatorStake, stakeAddr } =
        await setup();
      await mintDinViaDeposit(dinCoordinator, user, STAKE_DEPOSIT_ETH);
      await dinToken.connect(user).approve(stakeAddr, ethers.MaxUint256);

      await dinValidatorStake.connect(user).stake(MIN_STAKE * 2n);
      await dinValidatorStake.connect(user).unstake(MIN_STAKE);
      await expect(
        dinValidatorStake.connect(user).unstake(MIN_STAKE)
      ).to.be.revertedWithCustomError(
        dinValidatorStake,
        "PendingWithdrawalExists"
      );
    });
  });

  describe("slashing", function () {
    it("slashes active stake via an authorized slasher", async function () {
      const { user, dinValidatorStake, slasherAddr } = await setup();
      await dinValidatorStake.connect(user).stake(MIN_STAKE);

      await setBalance(slasherAddr, ethers.parseEther("1"));
      const slasherSigner = await ethers.getImpersonatedSigner(slasherAddr);

      const slashAmount = MIN_STAKE / 2n;
      await dinValidatorStake
        .connect(slasherSigner)
        .slash(user.address, slashAmount, ethers.id("test-reason"));

      expect(await dinValidatorStake.getStake(user.address)).to.equal(
        MIN_STAKE - slashAmount
      );
    });

    it("slashes pending withdrawals when active stake is exhausted", async function () {
      const { user, dinValidatorStake, slasherAddr } = await setup();
      await dinValidatorStake.connect(user).stake(MIN_STAKE);
      await dinValidatorStake.connect(user).unstake(MIN_STAKE);

      await setBalance(slasherAddr, ethers.parseEther("1"));
      const slasherSigner = await ethers.getImpersonatedSigner(slasherAddr);

      await dinValidatorStake
        .connect(slasherSigner)
        .slash(user.address, MIN_STAKE, ethers.id("test-reason"));

      const info = await dinValidatorStake.validators(user.address);
      expect(info.activeStake).to.equal(0n);
      expect(info.pendingWithdrawals).to.equal(0n);
    });

    it("reverts slash from an unauthorized address", async function () {
      const { user, other, dinValidatorStake } = await setup();
      await dinValidatorStake.connect(user).stake(MIN_STAKE);
      await expect(
        dinValidatorStake
          .connect(other)
          .slash(user.address, MIN_STAKE, ethers.id("test"))
      ).to.be.revertedWithCustomError(dinValidatorStake, "NotSlasherContract");
    });
  });

  describe("blacklisting", function () {
    it("owner can blacklist a validator and block further activity", async function () {
      const { deployer, user, dinValidatorStake } = await setup();
      await dinValidatorStake.connect(user).stake(MIN_STAKE);

      await dinValidatorStake.connect(deployer).blacklistValidator(user.address);
      expect(await dinValidatorStake.isValidatorActive(user.address)).to.equal(
        false
      );
      await expect(
        dinValidatorStake.connect(user).unstake(MIN_STAKE)
      ).to.be.revertedWithCustomError(dinValidatorStake, "ValidatorIsBlacklisted");
    });

    it("owner can unblacklist and restore Active status", async function () {
      const { deployer, user, dinValidatorStake } = await setup();
      await dinValidatorStake.connect(user).stake(MIN_STAKE);
      await dinValidatorStake.connect(deployer).blacklistValidator(user.address);

      await dinValidatorStake
        .connect(deployer)
        .unblacklistValidator(user.address);
      expect(await dinValidatorStake.isValidatorActive(user.address)).to.equal(
        true
      );
    });

    it("non-owner cannot blacklist", async function () {
      const { user, other, dinValidatorStake } = await setup();
      await expect(
        dinValidatorStake.connect(other).blacklistValidator(user.address)
      ).to.be.revertedWithCustomError(
        dinValidatorStake,
        "OwnableUnauthorizedAccount"
      );
    });

    it("reverts unblacklist on a validator that is not blacklisted", async function () {
      const { deployer, user, dinValidatorStake } = await setup();
      await expect(
        dinValidatorStake.connect(deployer).unblacklistValidator(user.address)
      ).to.be.revertedWithCustomError(
        dinValidatorStake,
        "ValidatorNotBlacklisted"
      );
    });
  });

  describe("slasher contract management", function () {
    it("only DIN_COORDINATOR can register slasher contracts", async function () {
      const { other, dinValidatorStake } = await setup();
      await expect(
        dinValidatorStake.connect(other).addSlasherContract(other.address)
      ).to.be.revertedWithCustomError(dinValidatorStake, "NotDINCoordinator");
    });

    it("reverts registering the same slasher twice", async function () {
      const { deployer, dinCoordinator, dinValidatorStake } = await setup();
      const MockSlasher = await ethers.getContractFactory("MockSlasher");
      const extra = await MockSlasher.deploy(deployer.address);
      await extra.waitForDeployment();
      const addr = await extra.getAddress();

      await dinCoordinator.addSlasherContract(addr);
      await expect(
        dinCoordinator.addSlasherContract(addr)
      ).to.be.revertedWithCustomError(
        dinValidatorStake,
        "SlasherContractAlreadyAdded"
      );
    });
  });
});
