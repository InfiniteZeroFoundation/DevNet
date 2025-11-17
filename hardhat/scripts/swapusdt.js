async function main() {
    const USDT_ADDRESS = "0xdAC17F958D2ee523a2206206994597C13D831ec7";
    const UNISWAP_ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D";
    const WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
    
    const USDT_ABI = ["function balanceOf(address) view returns (uint256)"];
    const UNISWAP_ABI = [
      "function getAmountsOut(uint256, address[]) view returns (uint256[])",
      "function swapExactETHForTokens(uint256,address[],address,uint256) payable returns (uint256[])"
    ];
    
    const [signer] = await ethers.getSigners();
    const usdt = new ethers.Contract(USDT_ADDRESS, USDT_ABI, ethers.provider);
    const router = new ethers.Contract(UNISWAP_ROUTER, UNISWAP_ABI, signer);
    
    // Check balance BEFORE
    const balanceBefore = await usdt.balanceOf(signer.address);
    console.log("USDT balance BEFORE swap:", ethers.formatUnits(balanceBefore, 6));
    
    // Define swap parameters
    const amountIn = ethers.parseEther("0.1");
    const amountsOut = await router.getAmountsOut(amountIn, [WETH_ADDRESS, USDT_ADDRESS]);
    const expectedUSDT = amountsOut[1]; // This is a BigInt
    
    // Set 1% slippage tolerance and 20 minute deadline
    const slippageTolerance = 100n; // 1% = 100 basis points - use 'n' suffix for BigInt
    const basisPoints = 10000n; // Use BigInt for all calculations
    const minAmountOut = (expectedUSDT * (basisPoints - slippageTolerance)) / basisPoints;
    const deadline = Math.floor(Date.now() / 1000) + 60 * 20;
    
    console.log(`Swapping ${ethers.formatEther(amountIn)} ETH for ~${ethers.formatUnits(expectedUSDT, 6)} USDT...`);
    
    try {
        // Execute swap (sending ETH with transaction)
        const tx = await router.swapExactETHForTokens(
          minAmountOut,
          [WETH_ADDRESS, USDT_ADDRESS],
          signer.address,
          deadline,
          { value: amountIn, gasLimit: 300000 }
        );
        
        console.log("Transaction sent:", tx.hash);
        await tx.wait();
        console.log("✅ Swap confirmed!");
        
        // Check balance AFTER
        const balanceAfter = await usdt.balanceOf(signer.address);
        console.log("USDT balance AFTER swap:", ethers.formatUnits(balanceAfter, 6));
        
        const received = balanceAfter - balanceBefore; // BigInt - BigInt is valid
        console.log(`Actually received: ${ethers.formatUnits(received, 6)} USDT`);
    } catch (error) {
        console.error("Swap failed:", error.message);
    }
}

main().catch(console.error);

// USDT balance BEFORE swap: 0.0
// Swapping 0.1 ETH for ~305.818413 USDT...
// Transaction sent: 0xc360a729441d54ce6070e11256528f9603ef073bf380d4e15458a1e768456dcd
// ✅ Swap confirmed!
// USDT balance AFTER swap: 305.818413
// Actually received: 305.818413 USDT