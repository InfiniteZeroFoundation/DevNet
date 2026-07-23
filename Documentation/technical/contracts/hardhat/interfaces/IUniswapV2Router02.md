# IUniswapV2Router02.sol — Interface Documentation

> **File:** `hardhat/contracts/interfaces/IUniswapV2Router02.sol`
> **Role:** partial Uniswap V2 router interface — **currently unused**

---

## 1. Contents

A hand-trimmed subset of the canonical Uniswap V2 `Router02` interface:

| Function | Purpose |
|----------|---------|
| `getAmountsIn(amountOut, path)` | Quote: input amounts required along a swap path for a desired output |
| `getAmountsOut(amountIn, path)` | Quote: output amounts along a path for a given input |
| `swapETHForExactTokens(amountOut, path, to, deadline)` | Swap ETH for an exact token amount (payable) |
| `WETH()` | The router's canonical WETH address |

---

## 2. Status: Unused

No contract, script, or test in the repository references this interface — it predates the upgradeable conversion and appears to be groundwork for a DEX-based DIN acquisition path (e.g. buying DIN via a Uniswap pool instead of, or alongside, `DinCoordinator.depositAndMint`) that was never built.

It compiles harmlessly (interfaces generate no bytecode of their own) and imposes no security surface.

## 3. Recommendation

Either remove it or move the idea to `Developer/` as a proposal. If a swap-based acquisition path is ever pursued, note that Optimism's primary DEX liquidity is on Uniswap **V3**/V4 — this V2 interface would likely be the wrong integration point anyway.
