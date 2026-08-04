export interface PlatformAddresses {
  dinToken: string;
  dinCoordinator: string;
  dinValidatorStake: string;
  dinModelRegistry: string;
  proxyAdmin?: string;
  implementations?: {
    dinToken?: string;
    dinCoordinator?: string;
    dinValidatorStake?: string;
    dinModelRegistry?: string;
  };
}
