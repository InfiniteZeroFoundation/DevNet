import { expect } from "chai";
import { ethers } from "hardhat";
import { Contract, Signer, BigNumberish } from "ethers";
import chalk from 'chalk';
import Table from 'cli-table3';

describe("Measure Gas Costs", function () {

    let DINRepresentative: any;
    let DINmodelOwner: any;
    let clients: any;
    let auditors: any;
    let aggregators: any;
    let dinCoordinator: any;
    let dinValidatorStake: any;
    let dinToken: any;
    let dinModelRegistry: any;
    let dinTaskCoordinator: any;
    let dinTaskAuditor: any; 56
    let mockUSDT: any;
    let USDTaddress: string = "0xdAC17F958D2ee523a2206206994597C13D831ec7";
    let wethAddress: string = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
    let uniswapRouterAddress: string = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D";
    let uniswapRouter: any;

    let USDT_DECIMALS = 6n;

    const BUY_AMOUNT_ETH = "1.0"; // ETH to spend buying DIN tokens per aggregator
    const MIN_STAKE = 1000000n * 10n ** 18n;
    let model_id;

    let curr_GI;

    before(async function () {
        const signers = await ethers.getSigners();
        DINRepresentative = signers[0];
        DINmodelOwner = signers[1];
        clients = signers.slice(2, 11); // 2 to 10
        auditors = signers.slice(50, 59); // 50 to 58
        aggregators = signers.slice(11, 23); // 11 to 22
    });

    describe("DIN contracts deployment gas costs", function () {
        it("should deploy DIN Coordinator contract", async function () {
            const DinCoordinator = await ethers.getContractFactory("DinCoordinator");
            dinCoordinator = await DinCoordinator.connect(DINRepresentative).deploy();
            const receipt = await dinCoordinator.deploymentTransaction()?.wait();
            const gas = receipt?.gasUsed ?? 0n;
            console.log(`Gas Used for DinCoordinator.deploy: ${gas.toString()}`);

            const dinTokenAddress = await dinCoordinator.dintoken();
            const DinToken = await ethers.getContractFactory("DinToken");
            dinToken = await DinToken.attach(dinTokenAddress);

        });

        it("should deploy DIN Validator Stake contract", async function () {
            const DinValidatorStake = await ethers.getContractFactory("DinValidatorStake");
            dinValidatorStake = await DinValidatorStake.connect(DINRepresentative).deploy(dinToken.getAddress(), dinCoordinator.getAddress());
            const receipt = await dinValidatorStake.deploymentTransaction()?.wait();
            const gas = receipt?.gasUsed ?? 0n;
            console.log(`Gas Used for DinValidatorStake.deploy: ${gas.toString()}`);
        });

        it("should add DIN Validator Stake contract to DIN Coordinator contract", async function () {
            const tx = await dinCoordinator.connect(DINRepresentative).add_dinvalidatorStakeContract(await dinValidatorStake.getAddress())
            const receipt = await tx.wait();
            const gas = receipt.gasUsed;
            console.log(`Gas Used for DinCoordinator.add_dinvalidatorStakeContract: ${gas.toString()}`);
        });

        it("should deploy DIN Model Registry contract", async function () {
            const DinModelRegistry = await ethers.getContractFactory("DINModelRegistry");
            dinModelRegistry = await DinModelRegistry.connect(DINRepresentative).deploy(dinValidatorStake.getAddress());
            const receipt = await dinModelRegistry.deploymentTransaction()?.wait();
            const gas = receipt?.gasUsed ?? 0n;
            console.log(`Gas Used for DinModelRegistry.deploy: ${gas.toString()}`);
        });

    });

    describe("USDT and ETH balances", function () {
        it("should get USDT and ETH balances", async function () {
            const MockUSDT = await ethers.getContractFactory("MockUSDT");
            mockUSDT = await MockUSDT.attach(USDTaddress);
            const usdtBalance = await mockUSDT.balanceOf(DINmodelOwner.address);
            const ethBalance = await ethers.provider.getBalance(DINmodelOwner.address);
            console.log(`USDT Balance: ${usdtBalance.toString()}`);
            console.log(`ETH Balance: ${ethBalance.toString()}`);
        });
    });

    describe("Buy USDT 3000", function () {

        const USDT_AMOUNT = 3000n; // 3000 USDT (as bigint)
        const USDT_DECIMALS = 6;   // USDT standard
        const SLIPPAGE_BPS = 1000n; // 10% slippage = 1000 basis points

        it("should buy USDT", async function () {
            const MockUSDT = await ethers.getContractFactory("MockUSDT");
            mockUSDT = await MockUSDT.attach(USDTaddress);
            const initialBalance = await mockUSDT.balanceOf(DINmodelOwner.address);
            const targetBalance = initialBalance + USDT_AMOUNT * 10n ** BigInt(USDT_DECIMALS);
            const ethBalance = await ethers.provider.getBalance(DINmodelOwner.address);
            console.log(`USDT Balance: ${initialBalance.toString()}`);
            console.log(`ETH Balance: ${ethBalance.toString()}`);

            console.log(`🎯 Target USDT balance: ${ethers.formatUnits(targetBalance, USDT_DECIMALS)}`);

            uniswapRouter = await ethers.getContractAt(
                "IUniswapV2Router02",
                uniswapRouterAddress
            );

            // 2️⃣ Calculate required ETH using router's getAmountsIn
            const path = [wethAddress, USDTaddress];

            // getAmountsIn requires you to pass the desired Output Amount as the first argument.
            const amountsIn = await uniswapRouter.connect(DINmodelOwner).getAmountsIn(
                USDT_AMOUNT * 10n ** BigInt(USDT_DECIMALS),
                path
            );
            const ethRequired = amountsIn[0]; // ETH amount in wei

            console.log(`💰 ETH required: ${ethers.formatEther(ethRequired)} ETH`);

            // 3️⃣ Check ETH balance + add slippage

            // calculates the maximum amount of ETH you are willing to spend, accounting for price movement (slippage) between the time you quote the price and when the transaction is mined.

            const ethWithSlippage = (ethRequired * (10000n + SLIPPAGE_BPS)) / 10000n; // +10%

            expect(ethBalance).to.be.gte(ethWithSlippage, "Insufficient ETH balance for swap");

            // 4️⃣ Approve router to spend WETH (if needed) - skip for ETH-native swaps
            // For swapETHForExactTokens, no approval needed (sending ETH directly)

            // 5️⃣ Set deadline (5 minutes from now)
            const block = await ethers.provider.getBlock("latest");

            // Date.now() returns milliseconds, block.timestamp is in seconds
            const deadline = (block?.timestamp ?? Math.floor(Date.now() / 1000)) + 300;

            // 6️⃣ Execute swap: swapETHForExactTokens
            const tx = await uniswapRouter.connect(DINmodelOwner)
                .swapETHForExactTokens(
                    USDT_AMOUNT * 10n ** BigInt(USDT_DECIMALS), // ✅ Desired output amoun
                    path, // ✅ Path from WETH to USDT
                    DINmodelOwner.address, // ✅ Recipient address
                    deadline, // ✅ Deadline for the swap
                    { value: ethWithSlippage } // ✅ ETH sent (with slippage buffer)
                );

            // Wait for confirmation and get receipt
            const receipt = await tx.wait(); // ⚠️ Waits for tx to be mined

            const gas = receipt?.gasUsed ?? 0n;
            console.log(`Gas Used for swapETHForExactTokens: ${gas.toString()}`);



            // 7️⃣ Verify final USDT balance meets target
            const finalBalance = await mockUSDT.balanceOf(DINmodelOwner.address);
            console.log(`✅ Final USDT balance: ${ethers.formatUnits(finalBalance, USDT_DECIMALS)}`);

            expect(finalBalance).to.be.gte(
                targetBalance,
                `USDT balance ${ethers.formatUnits(finalBalance, USDT_DECIMALS)} < target ${ethers.formatUnits(targetBalance, USDT_DECIMALS)}`
            );
        });

        it("should loop buying USDT until target balance reached (retry logic)", async function () {
            // Mimics Python while-loop: keep buying 3000 USDT until target met
            const initialBalance = await mockUSDT.balanceOf(DINmodelOwner.address);
            const targetBalance = initialBalance + USDT_AMOUNT * 10n ** BigInt(USDT_DECIMALS);

            let currentBalance = initialBalance;
            const MAX_RETRIES = 5;
            let retries = 0;

            while (currentBalance < targetBalance && retries < MAX_RETRIES) {
                console.log(`🔄 Attempt ${retries + 1}: Current=${ethers.formatUnits(currentBalance, USDT_DECIMALS)}, Target=${ethers.formatUnits(targetBalance, USDT_DECIMALS)}`);

                // Calculate ETH needed for remaining USDT
                const remainingUSDT = targetBalance - currentBalance;
                const path = [wethAddress, USDTaddress];

                const amountsIn = await uniswapRouter.connect(DINmodelOwner).getAmountsIn(remainingUSDT, path);
                const ethRequired = amountsIn[0];
                const ethWithSlippage = (ethRequired * 110n) / 100n; // +10%

                const block = await ethers.provider.getBlock("latest");
                const deadline = (block?.timestamp ?? Math.floor(Date.now() / 1000)) + 300;

                try {
                    const tx = await uniswapRouter.connect(DINmodelOwner)
                        .swapETHForExactTokens(
                            remainingUSDT,
                            path,
                            DINmodelOwner.address,
                            deadline,
                            { value: ethWithSlippage }
                        );
                    await tx.wait();

                    currentBalance = await mockUSDT.balanceOf(DINmodelOwner.address);
                    console.log(`✅ After swap: ${ethers.formatUnits(currentBalance, USDT_DECIMALS)} USDT`);
                } catch (error: any) {
                    console.error(`❌ Swap failed: ${error.message}`);
                    // Optional: break or continue based on error type
                    break;
                }

                retries++;
            }

            // Final assertion
            const finalBalance = await mockUSDT.balanceOf(DINmodelOwner.address);
            expect(finalBalance).to.be.gte(
                targetBalance,
                `Failed to reach target after ${retries} attempts`
            );
        });

    });


    describe("Deploy Model Owner Contracts", function () {
        it("should deploy DINTaskCoordinator and DINTaskAuditor", async function () {
            const DINTaskCoordinator = await ethers.getContractFactory("DINTaskCoordinator");
            dinTaskCoordinator = await DINTaskCoordinator.connect(DINmodelOwner).deploy(dinValidatorStake.getAddress());
            const receipt = await dinTaskCoordinator.deploymentTransaction()?.wait();
            const gas = receipt?.gasUsed ?? 0n;
            console.log(`Gas Used for DinTaskCoordinator.deploy: ${gas.toString()}`);

            const DINTaskAuditor = await ethers.getContractFactory("DINTaskAuditor");
            dinTaskAuditor = await DINTaskAuditor.connect(DINmodelOwner).deploy(mockUSDT.getAddress(), dinValidatorStake.getAddress(), dinTaskCoordinator.getAddress());
            const receipt2 = await dinTaskAuditor.deploymentTransaction()?.wait();
            const gas2 = receipt2?.gasUsed ?? 0n;
            console.log(`Gas Used for DinTaskAuditor.deploy: ${gas2.toString()}`);


            const tx = await dinTaskCoordinator.setDINTaskAuditorContract(dinTaskAuditor.getAddress())
            const receipt3 = await tx.wait();
            const gas3 = receipt3?.gasUsed ?? 0n;
            console.log(`Gas Used for DinTaskCoordinator.setDINTaskAuditorContract: ${gas3.toString()}`);

        });

    });

    // ============================================================================
    // 💸 MODEL OWNER: DEPOSIT REWARD
    // ============================================================================

    describe("Model Owner deposit reward in din-task-auditor", function () {
        it("should deposit reward in din-task-auditor", async function () {

            const REWARD_AMOUNT = 1000n;
            const rewardAmountWei = REWARD_AMOUNT * 10n ** USDT_DECIMALS;

            // Check balance
            const senderBalance = await mockUSDT.connect(DINmodelOwner).balanceOf(
                await DINmodelOwner.getAddress()
            );
            expect(senderBalance).to.be.gte(rewardAmountWei, "Insufficient USDT balance");

            // Handle USDT allowance (reset pattern for compatibility)
            const currentAllowance = await mockUSDT.connect(DINmodelOwner).allowance(
                await DINmodelOwner.getAddress(),
                await dinTaskAuditor.getAddress()
            );

            if (currentAllowance > 0n && currentAllowance !== rewardAmountWei) {
                console.log(`⚠️ Resetting existing allowance of ${ethers.formatUnits(currentAllowance, USDT_DECIMALS)} USDT to 0`);
                const tx = await mockUSDT.connect(DINmodelOwner).approve(
                    await dinTaskAuditor.getAddress(),
                    0
                );
                const receipt = await tx.wait();
                console.log(`⛽ Gas Used for USDT.approve(0): ${receipt.gasUsed.toString()}`);
            }

            if (currentAllowance !== rewardAmountWei) {
                console.log(`✅ Approving DINTaskAuditor to spend ${ethers.formatUnits(rewardAmountWei, USDT_DECIMALS)} USDT`);
                const tx = await mockUSDT.connect(DINmodelOwner).approve(
                    await dinTaskAuditor.getAddress(),
                    rewardAmountWei
                );
                const receipt = await tx.wait();
                console.log(`⛽ Gas Used for USDT.approve: ${receipt.gasUsed.toString()}`);
            }

            // Log pre-deposit state
            const usdtBalance = await mockUSDT.connect(DINmodelOwner).balanceOf(
                await DINmodelOwner.getAddress()
            );
            const usdtAllowance = await mockUSDT.connect(DINmodelOwner).allowance(
                await DINmodelOwner.getAddress(),
                await dinTaskAuditor.getAddress()
            );
            console.log(`💵 USDT Balance: ${ethers.formatUnits(usdtBalance, USDT_DECIMALS)}`);
            console.log(`🔐 USDT Allowance: ${ethers.formatUnits(usdtAllowance, USDT_DECIMALS)}`);

            const tx = await dinTaskAuditor.connect(DINmodelOwner).depositReward(rewardAmountWei);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for DINTaskAuditor.depositReward: ${receipt.gasUsed.toString()}`);

            // Optional: Verify reward was deposited
            const auditorBalance = await mockUSDT.balanceOf(await dinTaskAuditor.getAddress());
            console.log(`🏦 Auditor USDT Balance: ${ethers.formatUnits(auditorBalance, USDT_DECIMALS)}`);

        });
    });


    describe("Add slashers ", function () {
        it("DINDAO - should add taskCoordinator as slasher", async function () {
            const tx = await dinCoordinator.connect(DINRepresentative).add_slasher_contract(await dinTaskCoordinator.getAddress());
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for adding taskCoordinator to DINCoordinator as slasher by DINDAO: ${receipt.gasUsed.toString()}`);

        });

        it("ModelOwner - should add taskCoordinator as slasher", async function () {
            const tx = await dinTaskCoordinator.connect(DINmodelOwner).setDINTaskCoordinatorAsSlasher();
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for adding taskCoordinator to DINCoordinator as slasher by ModelOwner: ${receipt.gasUsed.toString()}`);

        });

        it("DINDAO - should add taskAuditor as slasher", async function () {
            const tx = await dinCoordinator.connect(DINRepresentative).add_slasher_contract(await dinTaskAuditor.getAddress());
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for adding taskAuditor to DINCoordinator as slasher by DINDAO: ${receipt.gasUsed.toString()}`);

        });

        it("ModelOwner - should add taskAuditor as slasher", async function () {
            const tx = await dinTaskCoordinator.connect(DINmodelOwner).setDINTaskAuditorAsSlasher();
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for adding taskAuditor to DINCoordinator as slasher by ModelOwner: ${receipt.gasUsed.toString()}`);

        });
    });

    describe("Submit Genesis Models", function () {
        it("should submit genesis model", async function () {

            const tx = await dinTaskCoordinator.connect(DINmodelOwner).setGenesisModelIpfsHash("QmcybqQuyS2CuPQuU4autUYHH2Sw6WXtaNsbtoWs3ni4UP");
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for submitting genesis model by ModelOwner: ${receipt.gasUsed.toString()}`);

            const tx2 = await dinTaskCoordinator.connect(DINmodelOwner).setTier2Score(0, 8);
            const receipt2 = await tx2.wait();
            console.log(`⛽ Gas Used for setting tier 2 score of genesis model by ModelOwner: ${receipt2.gasUsed.toString()}`);

        });
    });

    describe("Register Model to Registry", function () {
        it("should register model to registry", async function () {

            const manifestCID = "QmQaPUfVAyQBrkRvHZWyH8tbNukmcgEmghYFGZA6LKo8tp";
            const isOpenSource = true;

            // Execute registration
            const tx = await dinModelRegistry.connect(DINmodelOwner).registerModel(
                manifestCID,
                await dinTaskCoordinator.getAddress(),
                await dinTaskAuditor.getAddress(),
                isOpenSource
            );
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for submitting task by ModelOwner: ${receipt.gasUsed.toString()}`);

            // Parse and verify event
            const eventFragment = dinModelRegistry.interface.getEvent("ModelRegistered");
            const registryAddress = (await dinModelRegistry.getAddress()).toLowerCase();
            const events = receipt.logs
                .filter((log: any) =>
                    log.address.toLowerCase() === registryAddress &&
                    log.topics[0] === eventFragment?.topicHash
                )
                .map((log: any) => dinModelRegistry.interface.parseLog(log));

            expect(events).to.have.lengthOf(1, "Should emit exactly one ModelRegistered event");

            const { args } = events[0];
            model_id = args.modelId;

            // Assertions
            expect(args.modelId).to.be.a("bigint", "modelId should be a uint");
            expect(args.owner.toLowerCase()).to.equal(
                (await DINmodelOwner.getAddress()).toLowerCase(),
                "Owner should match signer"
            );
            expect(args.isOpenSource).to.equal(isOpenSource, "isOpenSource should match input");
            expect(args.manifestCID).to.equal(manifestCID, "Manifest CID should match");


        });
    });


    describe("Start GI", function () {
        it("should start global iteration", async function () {
            const tx = await dinTaskCoordinator.connect(DINmodelOwner).startGI(1, 3);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for starting global iteration by ModelOwner: ${receipt.gasUsed.toString()}`);
            curr_GI = 1;

        });
    });

    describe("Aggregators Open", function () {
        it("should open aggregators registration", async function () {
            const tx = await dinTaskCoordinator.connect(DINmodelOwner).startDINaggregatorsRegistration(1);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for opening aggregators registration by ModelOwner: ${receipt.gasUsed.toString()}`);

        });
    });

    describe("Aggregators Reg Loop", function () {
        it("should loop aggregators registration", async function () {

            for (const aggregator of aggregators) {

                const aggAddress = await aggregator.getAddress();
                console.log(`\n🔄 Processing Aggregator: ${aggAddress}`);
                console.log("─".repeat(60));

                const initialEthBalance = await ethers.provider.getBalance(aggAddress);
                const initialDinBalance = await dinToken.balanceOf(aggAddress);

                console.log(`💰 ETH Balance: ${ethers.formatEther(initialEthBalance)} ETH`);
                console.log(`🪙 DIN Balance: ${ethers.formatEther(initialDinBalance)} DIN`);

                if (initialDinBalance < MIN_STAKE) {
                    console.log(`⚠️  DIN balance (${ethers.formatEther(initialDinBalance)}) < MIN_STAKE (${ethers.formatEther(MIN_STAKE)})`);
                    console.log(`🛒 Buying DIN tokens for ${BUY_AMOUNT_ETH} ETH...`);

                    const buyAmountWei = ethers.parseEther(BUY_AMOUNT_ETH);
                    const currentEthBalance = await ethers.provider.getBalance(aggAddress);

                    // Ensure enough ETH for purchase + gas buffer
                    const ethWithBuffer = buyAmountWei + ethers.parseUnits("0.01", "ether"); // 0.01 ETH gas buffer
                    expect(currentEthBalance).to.be.gte(ethWithBuffer, "Insufficient ETH for DIN purchase + gas");

                    // Execute depositAndMint (assuming this mints DIN tokens for ETH)
                    const buyTx = await dinCoordinator
                        .connect(aggregator)
                        .depositAndMint({ value: buyAmountWei });

                    const buyReceipt = await buyTx.wait();
                    console.log(`⛽ Gas Used for depositAndMint: ${buyReceipt.gasUsed.toString()}`);

                    // Verify DIN tokens were received
                    const postBuyDinBalance = await dinToken.balanceOf(aggAddress);
                    console.log(`✅ DIN Balance after purchase: ${ethers.formatEther(postBuyDinBalance)} DIN`);

                    expect(postBuyDinBalance).to.be.gt(initialDinBalance, "DIN balance should increase after purchase");
                }

                const currentDinBalance = await dinToken.balanceOf(aggAddress);

                if (currentDinBalance < MIN_STAKE) {
                    console.log(`❌ Aggregator DIN balance (${ethers.formatEther(currentDinBalance)}) still < MIN_STAKE (${ethers.formatEther(MIN_STAKE)})`);
                    console.log(`⏭️  Skipping registration for ${aggAddress}`);
                    continue; // Skip to next aggregator
                }

                console.log(`✅ Aggregator has sufficient DIN balance for staking`);

                const currentAllowance = await dinToken.allowance(aggAddress, await dinValidatorStake.getAddress());

                if (currentAllowance < MIN_STAKE) {
                    console.log(`🔐 Approving ValidatorStake to spend ${ethers.formatEther(MIN_STAKE)} DIN...`);

                    const approveTx = await dinToken
                        .connect(aggregator)
                        .approve(await dinValidatorStake.getAddress(), MIN_STAKE);

                    const approveReceipt = await approveTx.wait();
                    console.log(`⛽ Gas Used for DIN.approve: ${approveReceipt.gasUsed.toString()}`);
                } else {
                    console.log(`✅ Approval already sufficient: ${ethers.formatEther(currentAllowance)} DIN`);
                }

                const currentStake = await dinValidatorStake.getStake(aggAddress);
                console.log(`📊 Current stake: ${ethers.formatEther(currentStake)} DIN`);

                if (currentStake < MIN_STAKE) {
                    console.log(`🎯 Staking ${ethers.formatEther(MIN_STAKE)} DIN tokens...`);

                    const stakeTx = await dinValidatorStake
                        .connect(aggregator)
                        .stake(MIN_STAKE);

                    const stakeReceipt = await stakeTx.wait();
                    console.log(`⛽ Gas Used for stake: ${stakeReceipt.gasUsed.toString()}`);

                    // Verify stake was updated
                    const newStake = await dinValidatorStake.getStake(aggAddress);
                    expect(newStake).to.be.gte(MIN_STAKE, "Stake should meet minimum after staking");
                    console.log(`✅ New stake: ${ethers.formatEther(newStake)} DIN`);
                } else {
                    console.log(`✅ Already staked: ${ethers.formatEther(currentStake)} DIN`);
                }


                const isRegistered = await dinTaskCoordinator.isDINAggregator(curr_GI, aggAddress);

                if (isRegistered) {
                    console.log(`⚠️  Aggregator ${aggAddress} already registered for GI: ${curr_GI}`);
                    console.log(`⏭️  Skipping registration`);
                    continue;
                }

                console.log(`✅ Aggregator not yet registered - proceeding with registration`);

                // 7️⃣ Register aggregator
                // ─────────────────────────────────────────────────────
                try {
                    console.log(`📝 Registering aggregator for GI: ${curr_GI}...`);

                    const registerTx = await dinTaskCoordinator.connect(aggregator).registerDINaggregator(curr_GI);

                    const registerReceipt = await registerTx.wait();
                    console.log(`⛽ Gas Used for registerDINaggregator: ${registerReceipt.gasUsed.toString()}`);

                    // ─────────────────────────────────────────────────────
                    // 9️⃣ Final verification
                    // ─────────────────────────────────────────────────────
                    const finalIsRegistered = await dinTaskCoordinator.isDINAggregator(curr_GI, aggAddress);
                    expect(finalIsRegistered).to.equal(true, "Aggregator should be registered after transaction");

                    console.log(`✅ Aggregator ${aggAddress} successfully registered!`);

                } catch (error: any) {
                    console.error(`❌ Registration failed for ${aggAddress}: ${error.message}`);

                    // Helpful debugging info
                    if (error.message?.includes("revert")) {
                        console.error("   → Possible reasons:");
                        console.error("     • Insufficient stake");
                        console.error("     • Already registered");
                        console.error("     • Invalid global identifier");
                        console.error("     • Access control (only owner can register)");
                    }

                    // Re-throw to fail the test, or use `continue` to skip and test others
                    throw error;
                }

                // ─────────────────────────────────────────────────────
                // 🔚 Log final state
                // ─────────────────────────────────────────────────────
                const finalEthBalance = await ethers.provider.getBalance(aggAddress);
                const finalDinBalance = await dinToken.balanceOf(aggAddress);
                const finalStake = await dinValidatorStake.getStake(aggAddress);

                console.log(`\n📋 Final State for ${aggAddress}:`);
                console.log(`   💰 ETH: ${ethers.formatEther(finalEthBalance)}`);
                console.log(`   🪙 DIN: ${ethers.formatEther(finalDinBalance)}`);
                console.log(`   🔒 Staked: ${ethers.formatEther(finalStake)} DIN`);
                console.log(`   ✅ Registered: ${await dinTaskCoordinator.isDINAggregator(curr_GI, aggAddress)}`);
            }

            // Optional: Final summary after loop
            console.log(`\n🎉 Aggregator registration loop completed`);


        });
    });

    describe("Aggregators Close", function () {
        it("should close aggregators registration", async function () {
            const tx = await dinTaskCoordinator.connect(DINmodelOwner).closeDINaggregatorsRegistration(1);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for closing aggregators registration by ModelOwner: ${receipt.gasUsed.toString()}`);

            const registered_aggregators = await dinTaskCoordinator.getDINtaskAggregators(curr_GI);
            console.log(`\n📋 Registered Aggregators for GI ${curr_GI}:`);
            console.log(`   ${registered_aggregators.length} aggregators registered`);
            console.log(`   ${registered_aggregators}`);

            expect(registered_aggregators.length).to.be.equal(12);

        });
    });

    describe("Auditors Open", function () {
        it("should open auditors registration", async function () {
            const tx = await dinTaskCoordinator.connect(DINmodelOwner).startDINauditorsRegistration(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for opening auditors registration by ModelOwner: ${receipt.gasUsed.toString()}`);

        });
    });

    describe(("Auditor Reg Loop"), function () {
        it("should loop auditors registration", async function () {

            for (const auditor of auditors) {

                const auditorAddress = await auditor.getAddress();
                console.log(`\n🔄 Processing Auditor: ${auditorAddress}`);
                console.log("─".repeat(60));

                const initialEthBalance = await ethers.provider.getBalance(auditorAddress);
                const initialDinBalance = await dinToken.balanceOf(auditorAddress);

                console.log(`💰 ETH Balance: ${ethers.formatEther(initialEthBalance)} ETH`);
                console.log(`🪙 DIN Balance: ${ethers.formatEther(initialDinBalance)} DIN`);

                if (initialDinBalance < MIN_STAKE) {
                    console.log(`⚠️  DIN balance (${ethers.formatEther(initialDinBalance)}) < MIN_STAKE (${ethers.formatEther(MIN_STAKE)})`);
                    console.log(`🛒 Buying DIN tokens for ${BUY_AMOUNT_ETH} ETH...`);

                    const buyAmountWei = ethers.parseEther(BUY_AMOUNT_ETH);
                    const currentEthBalance = await ethers.provider.getBalance(auditorAddress);

                    // Ensure enough ETH for purchase + gas buffer
                    const ethWithBuffer = buyAmountWei + ethers.parseUnits("0.01", "ether"); // 0.01 ETH gas buffer
                    expect(currentEthBalance).to.be.gte(ethWithBuffer, "Insufficient ETH for DIN purchase + gas");

                    // Execute depositAndMint (assuming this mints DIN tokens for ETH)
                    const buyTx = await dinCoordinator
                        .connect(auditor)
                        .depositAndMint({ value: buyAmountWei });

                    const buyReceipt = await buyTx.wait();
                    console.log(`⛽ Gas Used for depositAndMint: ${buyReceipt.gasUsed.toString()}`);

                    // Verify DIN tokens were received
                    const postBuyDinBalance = await dinToken.balanceOf(auditorAddress);
                    console.log(`✅ DIN Balance after purchase: ${ethers.formatEther(postBuyDinBalance)} DIN`);

                    expect(postBuyDinBalance).to.be.gt(initialDinBalance, "DIN balance should increase after purchase");
                }

                const currentDinBalance = await dinToken.balanceOf(auditorAddress);

                if (currentDinBalance < MIN_STAKE) {
                    console.log(`❌ Auditor DIN balance (${ethers.formatEther(currentDinBalance)}) still < MIN_STAKE (${ethers.formatEther(MIN_STAKE)})`);
                    console.log(`⏭️  Skipping registration for ${auditorAddress}`);
                    continue; // Skip to next aggregator
                }

                console.log(`✅ Auditor has sufficient DIN balance for staking`);

                const currentAllowance = await dinToken.allowance(auditorAddress, await dinValidatorStake.getAddress());

                if (currentAllowance < MIN_STAKE) {
                    console.log(`🔐 Approving ValidatorStake to spend ${ethers.formatEther(MIN_STAKE)} DIN...`);

                    const approveTx = await dinToken
                        .connect(auditor)
                        .approve(await dinValidatorStake.getAddress(), MIN_STAKE);

                    const approveReceipt = await approveTx.wait();
                    console.log(`⛽ Gas Used for DIN.approve: ${approveReceipt.gasUsed.toString()}`);
                } else {
                    console.log(`✅ Approval already sufficient: ${ethers.formatEther(currentAllowance)} DIN`);
                }

                const currentStake = await dinValidatorStake.getStake(auditorAddress);
                console.log(`📊 Current stake: ${ethers.formatEther(currentStake)} DIN`);

                if (currentStake < MIN_STAKE) {
                    console.log(`🎯 Staking ${ethers.formatEther(MIN_STAKE)} DIN tokens...`);

                    const stakeTx = await dinValidatorStake
                        .connect(auditor)
                        .stake(MIN_STAKE);

                    const stakeReceipt = await stakeTx.wait();
                    console.log(`⛽ Gas Used for stake: ${stakeReceipt.gasUsed.toString()}`);

                    // Verify stake was updated
                    const newStake = await dinValidatorStake.getStake(auditorAddress);
                    expect(newStake).to.be.gte(MIN_STAKE, "Stake should meet minimum after staking");
                    console.log(`✅ New stake: ${ethers.formatEther(newStake)} DIN`);
                } else {
                    console.log(`✅ Already staked: ${ethers.formatEther(currentStake)} DIN`);
                }


                const isRegistered = await dinTaskAuditor.isRegisteredAuditor(curr_GI, auditorAddress);

                if (isRegistered) {
                    console.log(`⚠️  Auditor ${auditorAddress} already registered for GI: ${curr_GI}`);
                    console.log(`⏭️  Skipping registration`);
                    continue;
                }

                console.log(`✅ Auditor not yet registered - proceeding with registration`);

                // 7️⃣ Register auditor
                // ─────────────────────────────────────────────────────
                try {
                    console.log(`📝 Registering auditor for GI: ${curr_GI}...`);

                    const registerTx = await dinTaskAuditor
                        .connect(auditor)
                        .registerDINAuditor(curr_GI);

                    const registerReceipt = await registerTx.wait();
                    console.log(`⛽ Gas Used for registerDINAuditor: ${registerReceipt.gasUsed.toString()}`);


                    // ─────────────────────────────────────────────────────
                    // 9️⃣ Final verification
                    // ─────────────────────────────────────────────────────
                    const finalIsRegistered = await dinTaskAuditor.isRegisteredAuditor(curr_GI, auditorAddress);
                    expect(finalIsRegistered).to.equal(true, "Auditor should be registered after transaction");

                    console.log(`✅ Auditor ${auditorAddress} successfully registered!`);

                } catch (error: any) {
                    console.error(`❌ Registration failed for ${auditorAddress}: ${error.message}`);

                    // Helpful debugging info
                    if (error.message?.includes("revert")) {
                        console.error("   → Possible reasons:");
                        console.error("     • Insufficient stake");
                        console.error("     • Already registered");
                        console.error("     • Invalid global identifier");
                        console.error("     • Access control (only owner can register)");
                    }

                    // Re-throw to fail the test, or use `continue` to skip and test others
                    throw error;
                }

                // ─────────────────────────────────────────────────────
                // 🔚 Log final state
                // ─────────────────────────────────────────────────────
                const finalEthBalance = await ethers.provider.getBalance(auditorAddress);
                const finalDinBalance = await dinToken.balanceOf(auditorAddress);
                const finalStake = await dinValidatorStake.getStake(auditorAddress);

                console.log(`\n📋 Final State for ${auditorAddress}:`);
                console.log(`   💰 ETH: ${ethers.formatEther(finalEthBalance)}`);
                console.log(`   🪙 DIN: ${ethers.formatEther(finalDinBalance)}`);
                console.log(`   🔒 Staked: ${ethers.formatEther(finalStake)} DIN`);
                console.log(`   ✅ Registered: ${await dinTaskAuditor.isRegisteredAuditor(curr_GI, auditorAddress)}`);
            }

            // Optional: Final summary after loop
            console.log(`\n🎉 Auditors registration loop completed`);

        });


    });


    describe("Auditors Close", function () {
        it("should close auditors registration", async function () {
            const tx = await dinTaskCoordinator.connect(DINmodelOwner).closeDINauditorsRegistration(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for closing auditors registration by ModelOwner: ${receipt.gasUsed.toString()}`);

            const registered_auditors = await dinTaskAuditor.getDINtaskAuditors(curr_GI);
            console.log(`\n📋 Registered Auditors for GI ${curr_GI}:`);
            console.log(`   ${registered_auditors.length} auditors registered`);
            console.log(`   ${registered_auditors}`);

            expect(registered_auditors.length).to.be.equal(9);

        });
    });

    describe(("Open LMS"), function () {
        it("should open LMS", async function () {
            const tx = await dinTaskCoordinator.connect(DINmodelOwner).startLMsubmissions(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for opening LMS by ModelOwner: ${receipt.gasUsed.toString()}`);

        });
    });

    describe("Clients Train", function () {
        it("should train clients", async function () {

            for (const client of clients) {

                const clientAddress = await client.getAddress();
                console.log(`\n🔄 Processing Client: ${clientAddress}`);
                console.log("─".repeat(60));


                const tx = await dinTaskAuditor.connect(client).submitLocalModel("QmXabcde123456789" + clientAddress, curr_GI);
                const receipt = await tx.wait();
                console.log(`⛽ Gas Used for LMS by Client: ${receipt.gasUsed.toString()}`);
            }

        });
    });

    describe("Clients LMS Close", function () {
        it("should close clients lms", async function () {
            const tx = await dinTaskCoordinator.connect(DINmodelOwner).closeLMsubmissions(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for closing LMS by ModelOwner: ${receipt.gasUsed.toString()}`);

            const lm_submissions = await dinTaskAuditor.connect(DINmodelOwner).getClientModels(curr_GI);
            console.log(`\n📋 Registered Models for GI ${curr_GI}:`);
            console.log(`   ${lm_submissions.length} models registered`);

            for (let i = 0; i < lm_submissions.length; i++) {
                console.log(` Client ${lm_submissions[i][0]} submitted model ${lm_submissions[i][1]}`);
            }


            expect(lm_submissions.length).to.be.equal(9);
        });
    });

    describe("Create Auditors Batches", function () {
        it("should create auditors batches", async function () {
            const tx = await dinTaskCoordinator.connect(DINmodelOwner).createAuditorsBatches(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for creating auditors batches by ModelOwner: ${receipt.gasUsed.toString()}`);

            const auditorBatchCount = await dinTaskAuditor.connect(DINmodelOwner).AuditorsBatchCount(curr_GI);

            const audit_testDataCIDs = ['QmYHc4Y6pmMKFohYDJXkFCCrLAQBUhwGuD6ebGZUxi34ea', 'QmSvTuP4XmcNnaYAqYkv6ewUKU7v2PCAnnLB9DqE7MTrAg', 'QmSdiTciKYBTxHKntjY3Pko8szD5D1nXVLU2mVWrsZhWdE', 'QmcLCGEz9FDHti6c2PPUqAh8rzGpQSwFAZi4QifcYkQB49', 'QmRZydYdpcHTpSSNy7MsX2K29KuUwEsoRxDkT9NEHqu6CQ', 'QmfBeoeqxb3SecGj4qUWcYYZ5AtCsUPyBn8deUj4RQofxw']

            for (let i = 0; i < auditorBatchCount; i++) {
                const tx = await dinTaskAuditor.connect(DINmodelOwner).assignAuditTestDataset(curr_GI, i, audit_testDataCIDs[i]);
                const receipt = await tx.wait();
                console.log(`⛽ Gas Used for assigning audit test dataset by ModelOwner: ${receipt.gasUsed.toString()}`);
            }

            const tx2 = await dinTaskCoordinator.connect(DINmodelOwner).setTestDataAssignedFlag(curr_GI, true);
            const receipt2 = await tx2.wait();
            console.log(`⛽ Gas Used for setting test data assigned flag by ModelOwner: ${receipt2.gasUsed.toString()}`);


            console.log(chalk.bold.green(`\n📋 Showing auditor batches for global iteration ${curr_GI}!`));
            console.log("─".repeat(80));


            console.log(chalk.bold.green(`📊 Auditor batches count:`), chalk.white(auditorBatchCount.toString()));

            const rawAuditBatches: any[] = [];

            for (let i = 0n; i < auditorBatchCount; i++) {
                const batch = await dinTaskAuditor.connect(DINmodelOwner).getAuditorsBatch(curr_GI, i);
                rawAuditBatches.push(batch);
            }

            interface AuditorBatch {
                batchId: bigint;
                auditors: string[];
                modelIndexes: bigint[];
                testCid: string;
            }

            const processedAuditBatches: AuditorBatch[] = rawAuditBatches.map((batch) => {
                const [batchId, auditors, modelIndexes, testCid] = batch;

                return {
                    batchId: BigInt(batchId),
                    auditors: Array.isArray(auditors) ? auditors.map((a: string) => a.toLowerCase()) : [],
                    modelIndexes: Array.isArray(modelIndexes) ? modelIndexes.map((m: any) => BigInt(m)) : [],
                    testCid: testCid && testCid !== "" ? testCid : "None",
                };
            });

            if (processedAuditBatches.length === 0) {
                console.log(chalk.yellow("⚠️  No auditor batches found."));
            }
            else {

                // Create formatted table using cli-table3
                const table = new Table({
                    head: [
                        chalk.magenta.bold("Batch ID"),
                        chalk.magenta.bold("Auditors"),
                        chalk.magenta.bold("Model Indexes"),
                        chalk.magenta.bold("Test CID"),
                    ],
                    colWidths: [12, 45, 25, 40],
                    wordWrap: true,
                    wrapOnWordBoundary: true,
                    style: {
                        head: ["magenta"],
                        border: ["gray"],
                    },
                });


                for (const batch of processedAuditBatches) {
                    const auditorsDisplay = batch.auditors.length > 0
                        ? batch.auditors.map((addr: string) => `${addr.slice(0, 6)}...${addr.slice(-4)}`).join(", ")
                        : "—";

                    const modelIndexesDisplay = batch.modelIndexes.length > 0
                        ? batch.modelIndexes.map((idx: bigint) => idx.toString()).join(", ")
                        : "—";

                    const testCidDisplay = batch.testCid !== "None" && batch.testCid.length > 0
                        ? (batch.testCid.length > 35 ? `${batch.testCid.slice(0, 32)}...` : batch.testCid)
                        : "—";

                    table.push([
                        batch.batchId.toString(),
                        auditorsDisplay,
                        modelIndexesDisplay,
                        testCidDisplay,
                    ]);
                }

                console.log(table.toString());
                console.log(chalk.green("✅ Auditor batches shown!"));

            }

        });
    });

    describe("Start LMS evaluation", async function () {

        it("should start LMS evaluation", async function () {

            const tx = await dinTaskCoordinator.connect(DINmodelOwner).startLMsubmissionsEvaluation(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for starting LMS evaluation by ModelOwner: ${receipt.gasUsed.toString()}`);

        });

    });


    describe("Submit LMS evaluations", async function () {
        it("should submit LMS evaluations", async function () {
            const auditorBatchCount = await dinTaskAuditor.connect(DINmodelOwner).AuditorsBatchCount(curr_GI);

            for (const auditor of auditors) {
                let found_any = false;
                for (let i = 0; i < auditorBatchCount; i++) {

                    const audit_batch = await dinTaskAuditor.connect(auditor).getAuditorsBatch(curr_GI, i);

                    // Destructure the tuple return value
                    const [batchId, batch_auditors, modelIndexes, testDataCid] = audit_batch;

                    const auditorAddress = await auditor.getAddress();
                    const isAuditorInBatch = batch_auditors
                        .map((addr: string) => addr.toLowerCase())
                        .includes(auditorAddress.toLowerCase());

                    if (isAuditorInBatch) {

                        for (const model_index of modelIndexes) {

                            found_any = true;
                            console.log(chalk.bold.green(`Evaluating LM ${model_index} from Audit batch ${i} by Auditor ${await auditor.getAddress()}!`));

                            let score = 90;
                            let eligible = true;

                            const tx = await dinTaskAuditor.connect(auditor).setAuditScorenEligibility(curr_GI, i, model_index, score, eligible);
                            const receipt = await tx.wait();
                            console.log(`⛽ Gas Used for submitting LMS evaluation by Auditor: ${receipt.gasUsed.toString()}`);
                        }

                    }

                }
            }

        });
    });

    describe("Show LMS Evaluations", function () {
        const SHOW_AUDITORS = true; // Show auditor evaluations
        const SHOW_MODELS = true;   // Show per-model evaluations

        it("should display LMS evaluations for current GI", async function () {
            console.log(chalk.bold.green(`\n📊 Showing LMS Evaluation for GI ${curr_GI}`));
            console.log("─".repeat(80));

            const rawLmSubmissions = await dinTaskAuditor.getClientModels(curr_GI);

            interface LmSubmission {
                modelIndex: bigint;
                client: string;
                modelCid: string;
                submittedAt: bigint;
                eligible: boolean;
                evaluated: boolean;
                approved: boolean;
                finalAvg: bigint;
            }

            const lmSubmissions: Map<bigint, LmSubmission> = new Map();

            for (let idx = 0n; idx < BigInt(rawLmSubmissions.length); idx++) {
                const sub = rawLmSubmissions[Number(idx)];
                const [client, modelCid, submittedAt, eligible, evaluated, approved, finalAvg] = sub;

                lmSubmissions.set(idx, {
                    modelIndex: idx,
                    client: client as string,
                    modelCid: modelCid as string,
                    submittedAt: BigInt(submittedAt),
                    eligible: eligible as boolean,
                    evaluated: evaluated as boolean,
                    approved: approved as boolean,
                    finalAvg: BigInt(finalAvg),
                });
            }

            const auditorBatchCount = await dinTaskAuditor.AuditorsBatchCount(curr_GI);
            console.log(chalk.dim(`📦 Auditor batches count: ${auditorBatchCount.toString()}`));

            // Data structures for mapping
            const modelIdxToBatchId: Map<bigint, bigint> = new Map();
            const modelIdxToTestCid: Map<bigint, string> = new Map();
            const batchIdToAuditors: Map<bigint, string[]> = new Map();
            const modelIdxToAuditors: Map<bigint, Set<string>> = new Map();
            const allAuditors: Set<string> = new Set();

            if (SHOW_AUDITORS || SHOW_MODELS) {
                for (let i = 0n; i < auditorBatchCount; i++) {
                    const batch = await dinTaskAuditor.getAuditorsBatch(curr_GI, i);
                    if (batch) {
                        const [batchId, batchAuditors, modelIndexes, testCid] = batch;

                        const auditorsList = (batchAuditors as string[]).map((a: string) => a.toLowerCase());
                        const modelIndexList = (modelIndexes as bigint[]).map((m: any) => BigInt(m));
                        const testCidStr = testCid as string;

                        batchIdToAuditors.set(BigInt(batchId), auditorsList);

                        for (const mIdx of modelIndexList) {
                            modelIdxToBatchId.set(mIdx, BigInt(batchId));
                            modelIdxToTestCid.set(mIdx, testCidStr);

                            if (!modelIdxToAuditors.has(mIdx)) {
                                modelIdxToAuditors.set(mIdx, new Set());
                            }
                            auditorsList.forEach((a: string) => modelIdxToAuditors.get(mIdx)?.add(a));
                        }

                        auditorsList.forEach((a: string) => allAuditors.add(a));
                    }
                }
            }


            // ─────────────────────────────────────────────────────
            // 4️⃣ Print LM Submissions Table
            // ─────────────────────────────────────────────────────
            const lmTable = new Table({
                head: [
                    chalk.magenta.bold("Model Index"),
                    chalk.magenta.bold("Client"),
                    chalk.magenta.bold("Model CID"),
                    chalk.magenta.bold("Submitted At"),
                    chalk.magenta.bold("Eligible"),
                    chalk.magenta.bold("Evaluated"),
                    chalk.magenta.bold("Approved"),
                    chalk.magenta.bold("Final Avg"),
                ],
                colWidths: [12, 42, 48, 20, 10, 10, 10, 12],
                wordWrap: true,
                style: { head: ["magenta"], border: ["gray"] },
            });

            for (const [, sub] of lmSubmissions) {
                lmTable.push([
                    sub.modelIndex.toString(),
                    sub.client.slice(0, 10) + "...",
                    sub.modelCid.slice(0, 15) + "...",
                    sub.submittedAt.toString(),
                    sub.eligible ? "✓" : "✗",
                    sub.evaluated ? "✓" : "✗",
                    sub.approved ? "✓" : "✗",
                    sub.finalAvg > 0n ? sub.finalAvg.toString() : "—",
                ]);
            }

            console.log(lmTable.toString());

            // ─────────────────────────────────────────────────────
            // 5️⃣ Build Per-Auditor Assigned Models (if SHOW_AUDITORS)
            // ─────────────────────────────────────────────────────
            interface AuditorAssignment {
                modelIndex: bigint;
                client: string;
                modelCid: string;
                batchId: bigint;
                hasVoted: boolean;
                isEligible: boolean;
                auditScores: bigint;
                testCid: string;
            }

            const assignedLmSubmissions: Map<string, AuditorAssignment[]> = new Map();

            if (SHOW_AUDITORS) {
                console.log(chalk.bold.cyan(`\n🔍 Auditor Evaluations for GI ${curr_GI}`));
                console.log("─".repeat(80));

                for (const auditorAddr of Array.from(allAuditors).sort()) {
                    const assignments: AuditorAssignment[] = [];

                    for (const [modelIdx, auditorsSet] of modelIdxToAuditors) {
                        if (!auditorsSet.has(auditorAddr)) continue;

                        const batchId = modelIdxToBatchId.get(modelIdx);
                        if (batchId === undefined) continue;

                        const [hasVoted, isEligible, auditScores] = await Promise.all([
                            dinTaskAuditor.hasAuditedLM(curr_GI, batchId, auditorAddr, modelIdx),
                            dinTaskAuditor.LMeligibleVote(curr_GI, batchId, auditorAddr, modelIdx),
                            dinTaskAuditor.auditScores(curr_GI, batchId, auditorAddr, modelIdx),
                        ]);

                        const lm = lmSubmissions.get(modelIdx);
                        assignments.push({
                            modelIndex: modelIdx,
                            client: lm?.client || "Unknown",
                            modelCid: lm?.modelCid || "N/A",
                            batchId,
                            hasVoted: hasVoted as boolean,
                            isEligible: isEligible as boolean,
                            auditScores: BigInt(auditScores),
                            testCid: modelIdxToTestCid.get(modelIdx) || "N/A",
                        });
                    }

                    assignedLmSubmissions.set(auditorAddr, assignments);

                    // Print per-auditor table
                    const auditorTable = new Table({
                        head: [
                            chalk.magenta.bold("ModelIdx"),
                            chalk.magenta.bold("Client"),
                            chalk.magenta.bold("Model CID"),
                            chalk.magenta.bold("Batch ID"),
                            chalk.magenta.bold("Voted"),
                            chalk.magenta.bold("Eligible"),
                            chalk.magenta.bold("Score"),
                            chalk.magenta.bold("Test CID"),
                        ],
                        colWidths: [10, 42, 48, 12, 10, 10, 10, 40],
                        wordWrap: true,
                        style: { head: ["magenta"], border: ["gray"] },
                    });

                    for (const assignment of assignments) {
                        auditorTable.push([
                            assignment.modelIndex.toString(),
                            assignment.client.slice(0, 10) + "...",
                            assignment.modelCid.slice(0, 15) + "...",
                            assignment.batchId.toString(),
                            assignment.hasVoted ? "✓" : "✗",
                            assignment.isEligible ? "✓" : "✗",
                            assignment.auditScores > 0n ? assignment.auditScores.toString() : "—",
                            assignment.testCid !== "N/A" && assignment.testCid.length > 35
                                ? assignment.testCid.slice(0, 32) + "..."
                                : assignment.testCid,
                        ]);
                    }

                    console.log(chalk.bold.yellow(`\n👤 Auditor: ${auditorAddr.slice(0, 10)}...${auditorAddr.slice(-8)}`));
                    console.log(auditorTable.toString());
                }
            }

            // ─────────────────────────────────────────────────────
            // 6️⃣ Print Per-Model Evaluation Tables (if SHOW_MODELS)
            // ─────────────────────────────────────────────────────
            if (SHOW_MODELS) {
                console.log(chalk.bold.cyan(`\n🤖 Per-Model Evaluations for GI ${curr_GI}`));
                console.log("─".repeat(80));

                for (const [modelIdx,] of lmSubmissions) {
                    const batchId = modelIdxToBatchId.get(modelIdx);
                    const auditorsForModel = Array.from(modelIdxToAuditors.get(modelIdx) || []).sort();

                    const modelEvalTable = new Table({
                        head: [
                            chalk.cyan.bold("Auditor"),
                            chalk.cyan.bold("Batch ID"),
                            chalk.cyan.bold("Voted"),
                            chalk.cyan.bold("Eligible"),
                            chalk.cyan.bold("Score"),
                        ],
                        colWidths: [42, 12, 10, 10, 10],
                        wordWrap: true,
                        style: { head: ["cyan"], border: ["gray"] },
                    });

                    if (auditorsForModel.length === 0) {
                        modelEvalTable.push(["—", batchId?.toString() || "—", "—", "—", "—"]);
                    } else {
                        for (const auditorAddr of auditorsForModel) {
                            if (batchId === undefined) continue;

                            const [hasVoted, isEligible, auditScores] = await Promise.all([
                                dinTaskAuditor.hasAuditedLM(curr_GI, batchId, auditorAddr, modelIdx),
                                dinTaskAuditor.LMeligibleVote(curr_GI, batchId, auditorAddr, modelIdx),
                                dinTaskAuditor.auditScores(curr_GI, batchId, auditorAddr, modelIdx),
                            ]);

                            modelEvalTable.push([
                                auditorAddr.slice(0, 10) + "..." + auditorAddr.slice(-8),
                                batchId.toString(),
                                (hasVoted as boolean) ? "✓" : "✗",
                                (isEligible as boolean) ? "✓" : "✗",
                                BigInt(auditScores) > 0n ? BigInt(auditScores).toString() : "—",
                            ]);
                        }
                    }

                    console.log(chalk.bold.white(`\n📊 Model Index: ${modelIdx.toString()}`));
                    console.log(modelEvalTable.toString());

                    const testCid = modelIdxToTestCid.get(modelIdx);
                    if (testCid && testCid !== "") {
                        console.log(chalk.dim(`   Test CID: ${testCid}`));
                    }
                }
            }

            console.log(chalk.green("\n✅ LMS evaluations displayed successfully!"));

        });

    });

    describe("Close LMS Evaluation", function () {

        it("should close LMS evaluation", async function () {

            const tx = await dinTaskCoordinator.connect(DINmodelOwner).closeLMsubmissionsEvaluation(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for closing LMS evaluation by ModelOwner: ${receipt.gasUsed.toString()}`);

        });

    });

    describe("Create T1NT2 Batches", function () {

        it("should create T1NT2 batches", async function () {

            console.log(chalk.bold.green("Creating Tier 1 & Tier 2 batches"));

            const tx = await dinTaskCoordinator.connect(DINmodelOwner).autoCreateTier1AndTier2(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for creating T1NT2 batches by ModelOwner: ${receipt.gasUsed.toString()}`);

        });

    });

    describe("Start T1 Aggregation", function () {

        it("should start T1 aggregation", async function () {

            console.log(chalk.bold.green("Starting T1 aggregation"));

            const tx = await dinTaskCoordinator.connect(DINmodelOwner).startT1Aggregation(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for starting T1 aggregation by ModelOwner: ${receipt.gasUsed.toString()}`);

        });

    });

    describe("Aggregate T1 Batches", function () {
        it("should aggregate T1 batches", async function () {

            console.log(chalk.bold.green(`\n🔄 Aggregating T1 Batches for GI ${curr_GI}`));
            const t1_batches_count = await dinTaskCoordinator.tier1BatchCount(curr_GI);

            console.log(chalk.cyan(`📦 T1 Batches Count: ${t1_batches_count.toString()}`));
            console.log("─".repeat(80));

            for (const aggregator of aggregators) {

                console.log(chalk.dim(`👤 Aggregator: ${aggregator.address}`));

                let found_batch = false


                for (let batchId = 0; batchId < t1_batches_count; batchId++) {

                    // Fetch batch data
                    const batch = await dinTaskCoordinator.getTier1Batch(curr_GI, batchId);
                    const [bid, validators, modelIndexes, finalized, testCid] = batch;

                    const validatorsList = (validators as string[]).map((v: string) => v.toLowerCase());

                    if (!validatorsList.includes(aggregator.address.toLowerCase())) {

                        continue;
                    }

                    found_batch = true;
                    console.log(chalk.bold.cyan(`\n📋 Processing T1 Batch ${bid.toString()}`));

                    const tx = await dinTaskCoordinator
                        .connect(aggregator)
                        .submitT1Aggregation(curr_GI, bid, "QmAggregatedCID" + bid.toString());
                    const receipt = await tx.wait();
                    console.log(`⛽ Gas Used for submitting T1 aggregation by Aggregator: ${receipt.gasUsed.toString()}`);


                }

                if (!found_batch) {
                    console.log(chalk.yellow(`\n⚠️  No T1 batches found for aggregator ${aggregator.address}`));
                } else {
                    console.log(chalk.green(`\n✅ T1 batch aggregation completed successfully for ${aggregator.address}`));
                }



            }

        });
    });

    describe("Close T1 Aggregation", function () {

        it("should close T1 aggregation", async function () {

            console.log(chalk.bold.green("Closing T1 aggregation"));

            const tx = await dinTaskCoordinator.connect(DINmodelOwner).finalizeT1Aggregation(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for closing T1 aggregation by ModelOwner: ${receipt.gasUsed.toString()}`);

        });

    });

    describe("Start T2 Aggregation", function () {

        it("should start T2 aggregation", async function () {

            console.log(chalk.bold.green("Starting T2 aggregation"));

            const tx = await dinTaskCoordinator.connect(DINmodelOwner).startT2Aggregation(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for starting T2 aggregation by ModelOwner: ${receipt.gasUsed.toString()}`);

        });

    });

    describe("Aggregate T2 Batches", function () {
        it("should aggregate T2 batches", async function () {

            console.log(chalk.bold.green(`\n🔄 Aggregating T2 Batches for GI ${curr_GI}`));
            const t2_batches_count = 1

            console.log(chalk.cyan(`📦 T2 Batches Count: ${t2_batches_count.toString()}`));
            console.log("─".repeat(80));

            for (const aggregator of aggregators) {

                console.log(chalk.dim(`👤 Aggregator: ${aggregator.address}`));

                let found_batch = false


                for (let batchId = 0; batchId < t2_batches_count; batchId++) {

                    // Fetch batch data
                    const batch = await dinTaskCoordinator.getTier2Batch(curr_GI, batchId);
                    const [bid, validators, modelIndexes, finalized, testCid] = batch;

                    const validatorsList = (validators as string[]).map((v: string) => v.toLowerCase());

                    if (!validatorsList.includes(aggregator.address.toLowerCase())) {

                        continue;
                    }

                    found_batch = true;
                    console.log(chalk.bold.cyan(`\n📋 Processing T2 Batch ${bid.toString()}`));

                    const tx = await dinTaskCoordinator
                        .connect(aggregator)
                        .submitT2Aggregation(curr_GI, bid, "QmAggregatedCIDT2" + bid.toString());
                    const receipt = await tx.wait();
                    console.log(`⛽ Gas Used for submitting T2 aggregation by Aggregator: ${receipt.gasUsed.toString()}`);


                }

                if (!found_batch) {
                    console.log(chalk.yellow(`\n⚠️  No T2 batches found for aggregator ${aggregator.address}`));
                } else {
                    console.log(chalk.green(`\n✅ T2 batch aggregation completed successfully for ${aggregator.address}`));
                }



            }

        });
    });

    describe("Close T2 Aggregation", function () {

        it("should close T2 aggregation", async function () {

            console.log(chalk.bold.green("Closing T2 aggregation"));

            const tx = await dinTaskCoordinator.connect(DINmodelOwner).finalizeT2Aggregation(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for closing T2 aggregation by ModelOwner: ${receipt.gasUsed.toString()}`);

        });

    });


    describe("Slash Auditors", function () {
        it("should slash auditors", async function () {

            console.log(chalk.bold.green("Slashing Auditors"));

            const tx = await dinTaskCoordinator.connect(DINmodelOwner).slashAuditors(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for slashing auditors by ModelOwner: ${receipt.gasUsed.toString()}`);

        });
    });

    describe("Slash Aggregators", function () {
        it("should slash aggregators", async function () {

            console.log(chalk.bold.green("Slashing Aggregators"));

            const tx = await dinTaskCoordinator.connect(DINmodelOwner).slashAggregators(curr_GI);
            const receipt = await tx.wait();
            console.log(`⛽ Gas Used for slashing aggregators by ModelOwner: ${receipt.gasUsed.toString()}`);

        });
    });

});