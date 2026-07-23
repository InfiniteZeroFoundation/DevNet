export interface PlatformAddresses {
  dinToken: string;
  dinCoordinator: string;
  dinValidatorStake: string;
  dinModelRegistry: string;
  proxyAdminToken?: string;
  proxyAdminCoordinator?: string;
  proxyAdminStake?: string;
  proxyAdminRegistry?: string;
  implementations?: {
    dinToken?: string;
    dinCoordinator?: string;
    dinValidatorStake?: string;
    dinModelRegistry?: string;
  };
}
