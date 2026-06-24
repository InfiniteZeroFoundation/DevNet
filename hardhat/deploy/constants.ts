export const PROXY_KIND = "transparent" as const;

export const PLATFORM_CONTRACTS = [
  "DinToken",
  "DinCoordinator",
  "DinValidatorStake",
  "DINModelRegistry",
] as const;

export type PlatformContractName = (typeof PLATFORM_CONTRACTS)[number];
