import { expect } from "chai";
import { ethers } from "hardhat";
import { DINModelRegistry } from "../typechain-types";

describe("DINModelRegistry", function () {
    let dinModelRegistry: DINModelRegistry;
    let owner: any;
    let otherAccount: any;

    beforeEach(async function () {
        [owner, otherAccount] = await ethers.getSigners();
        const DINModelRegistry = await ethers.getContractFactory("DINModelRegistry");
        dinModelRegistry = await DINModelRegistry.deploy();
    });

    it("Should set the right proprietaryFee in constructor", async function () {
        const fee = await dinModelRegistry.proprietaryFee();
        expect(fee).to.equal(ethers.parseEther("0.01"));
    });

    it("Should allow daoAdmin to update proprietaryFee", async function () {
        const newFee = ethers.parseEther("0.02");
        await dinModelRegistry.setProprietaryFee(newFee);
        expect(await dinModelRegistry.proprietaryFee()).to.equal(newFee);
    });

    it("Should fail if non-admin tries to update proprietaryFee", async function () {
        const newFee = ethers.parseEther("0.02");
        await expect(
            dinModelRegistry.connect(otherAccount).setProprietaryFee(newFee)
        ).to.be.revertedWith("Only DAO admin");
    });
});
