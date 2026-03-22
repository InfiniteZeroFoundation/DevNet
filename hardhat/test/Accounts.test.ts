import { expect } from "chai";
import { ethers } from "hardhat";

describe("Accounts", function () {
    let DINRepresentative: any;
    let DINmodelOwner: any;
    let clients: any;
    let auditors: any;
    let aggregators: any;

    before(async function () {
        const signers = await ethers.getSigners();
        DINRepresentative = signers[0];
        DINmodelOwner = signers[1];
        clients = signers.slice(2, 11);      // indices 2-10 → 9 signers
        auditors = signers.slice(50, 59);    // indices 50-58 → 9 signers
        aggregators = signers.slice(11, 23); // indices 11-22 → 12 signers
    });

    describe("Accounts", function () {
        it("DINRepresentative: should be a valid signer", function () {
            expect(DINRepresentative.address).to.be.properAddress;
        });

        it("DINmodelOwner: should be a valid signer", function () {
            expect(DINmodelOwner.address).to.be.properAddress;
        });

        it("clients: should have 9 accounts", function () {
            expect(clients).to.have.lengthOf(9);
        });

        it("auditors: should have 9 accounts", function () {
            expect(auditors).to.have.lengthOf(9);
        });

        it("aggregators: should have 12 accounts", function () {
            expect(aggregators).to.have.lengthOf(12);
        });
    });
});