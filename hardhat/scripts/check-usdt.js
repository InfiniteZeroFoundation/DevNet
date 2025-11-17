async function main() {
    // Real USDT address
    const USDT_ADDRESS = "0xdAC17F958D2ee523a2206206994597C13D831ec7";
    
    // Get USDT contract
    const USDT_ABI = [
      "function balanceOf(address) view returns (uint256)",
      "function decimals() view returns (uint8)",
      "function symbol() view returns (string)"
    ];
    
    // Use 'ethers' consistently (injected by Hardhat)
    const usdt = new ethers.Contract(USDT_ADDRESS, USDT_ABI, ethers.provider);
    
    // Get your test account
    const [signer] = await ethers.getSigners();
    console.log("Test account:", signer.address);
    
    // Check USDT balance
    const balance = await usdt.balanceOf(signer.address);
    console.log("USDT balance:", ethers.formatUnits(balance, 6)); // FIXED
    
    // If you want to swap ETH for USDT using Uniswap
    const UNISWAP_ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D";
    const WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
    
    const UNISWAP_ABI = [
      "function getAmountsOut(uint256, address[]) view returns (uint256[] memory)",
      "function swapExactETHForTokens(uint256,address[],address,uint256) payable"
    ];
    
    const router = new ethers.Contract(UNISWAP_ROUTER, UNISWAP_ABI, signer);
    
    // Get quote for 0.1 ETH
    const amountIn = ethers.parseEther("0.1"); // FIXED
    try {
      const amounts = await router.getAmountsOut(amountIn, [WETH_ADDRESS, USDT_ADDRESS]);
      const expectedUSDT = amounts[1];
      console.log("Expected USDT for 0.1 ETH:", ethers.formatUnits(expectedUSDT, 6)); // FIXED
    } catch (error) {
      console.log("Could not get quote (likely need to provide liquidity first)");
    }
  }
  
  main()
    .then(() => process.exit(0))
    .catch((error) => {
      console.error(error);
      process.exit(1);
    });