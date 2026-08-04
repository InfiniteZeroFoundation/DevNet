import { ContractFactory } from "ethers";
import { upgrades } from "hardhat";
import * as fs from "fs";
import * as path from "path";

import { PROXY_KIND } from "./constants";
import type { PlatformAddresses } from "./types";

const DEPLOYMENTS_DIR = path.join(__dirname, "..", "deployments");

export async function deployTransparentProxy<T extends ContractFactory>(
  factory: T,
  initArgs: unknown[] = [],
  initializer = "initialize"
) {
  const proxy = await upgrades.deployProxy(factory, initArgs, {
    kind: PROXY_KIND,
    initializer,
  });
  await proxy.waitForDeployment();
  return proxy;
}

export async function upgradeTransparentProxy<T extends ContractFactory>(
  proxyAddress: string,
  factory: T
) {
  const upgraded = await upgrades.upgradeProxy(proxyAddress, factory, {
    kind: PROXY_KIND,
  });
  await upgraded.waitForDeployment();
  return upgraded;
}

export function deploymentPath(network: string): string {
  return path.join(DEPLOYMENTS_DIR, `${network}.json`);
}

export function savePlatformAddresses(
  network: string,
  addresses: PlatformAddresses
): void {
  fs.mkdirSync(DEPLOYMENTS_DIR, { recursive: true });
  fs.writeFileSync(
    deploymentPath(network),
    JSON.stringify(addresses, null, 2) + "\n"
  );
}

export function loadPlatformAddresses(network: string): PlatformAddresses {
  const file = deploymentPath(network);
  if (!fs.existsSync(file)) {
    throw new Error(
      `No deployment file at ${file}. Run the platform deploy script first.`
    );
  }
  return JSON.parse(fs.readFileSync(file, "utf8")) as PlatformAddresses;
}

export async function getProxyAdminAddress(
  proxyAddress: string
): Promise<string> {
  return upgrades.erc1967.getAdminAddress(proxyAddress);
}
