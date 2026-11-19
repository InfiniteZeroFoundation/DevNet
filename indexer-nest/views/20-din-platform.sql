-- The platform contracts' view-shaped entities from PR 29's schema.graphql (613f5b2): the ones a
-- handler loads, changes and saves again, so the answer is the latest row per key, not an event.
-- Ordering is (block_number, log_index), which is the chain's own order across tables.
-- `uint256` columns come as exact text; `<col>_dec` is the DECIMAL(38,0) form used for numbers.

-- StakeGovernance (singleton). Each of three events moves one field; the subgraph seeds the
-- initialize() defaults (10 DIN, 7 days, 0) and only has a row once one of them has fired.
CREATE VIEW stake_governance AS
  WITH e AS (
    SELECT block_number, log_index, block_timestamp, 'min_stake' AS k, CAST("newMinStake" AS DECIMAL(38, 0)) AS v
    FROM stake__min_stake_updated
    UNION ALL
    SELECT block_number, log_index, block_timestamp, 'unbonding_period', CAST("newPeriod" AS DECIMAL(38, 0))
    FROM stake__unbonding_period_updated
    UNION ALL
    SELECT block_number, log_index, block_timestamp, 'max_concurrent', CAST("value" AS DECIMAL(38, 0))
    FROM stake__max_concurrent_registrations_per_stake_unit_updated
  ),
  latest AS (
    SELECT k, v, ROW_NUMBER() OVER (PARTITION BY k ORDER BY block_number DESC, log_index DESC) AS rn FROM e
  )
  SELECT coalesce(max(CASE WHEN k = 'min_stake' THEN v END), CAST('10000000000000000000' AS DECIMAL(38, 0))) AS min_stake,
         coalesce(max(CASE WHEN k = 'unbonding_period' THEN v END), CAST(604800 AS DECIMAL(38, 0))) AS unbonding_period,
         coalesce(max(CASE WHEN k = 'max_concurrent' THEN v END), CAST(0 AS DECIMAL(38, 0))) AS max_concurrent_registrations_per_stake_unit,
         (SELECT max(block_number) FROM e) AS updated_at_block,
         to_timestamp((SELECT max(block_timestamp) FROM e)) AS updated_at
  FROM latest WHERE rn = 1
  HAVING count(*) > 0;

-- ModelStakeBounds: the latest min and max per model.
CREATE VIEW model_stake_bounds AS
  SELECT model_id, min_stake, max_stake, updated_at_block, updated_at
  FROM (
    SELECT "modelId_dec" AS model_id, "min_dec" AS min_stake, "max_dec" AS max_stake,
           block_number AS updated_at_block, to_timestamp(block_timestamp) AS updated_at,
           ROW_NUMBER() OVER (PARTITION BY "modelId" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM stake__model_stake_bounds_updated
  ) b WHERE rn = 1;

-- SlasherRegistration, keyed (slasher, source contract). DinValidatorStake and DinCoordinator both
-- emit Added and Removed for every slasher, and the subgraph keeps one row per source. An Added
-- starts a fresh row (so a re-add clears the removal); a Removed with no row to find is ignored.
CREATE VIEW slasher_registrations AS
  WITH ev AS (
    SELECT slasher, address AS source_contract, 1 AS added, block_number, log_index, block_timestamp FROM stake__slasher_contract_added
    UNION ALL SELECT slasher, address, 1, block_number, log_index, block_timestamp FROM coordinator__slasher_contract_added
    UNION ALL SELECT slasher, address, 0, block_number, log_index, block_timestamp FROM stake__slasher_contract_removed
    UNION ALL SELECT slasher, address, 0, block_number, log_index, block_timestamp FROM coordinator__slasher_contract_removed
  ),
  r AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY slasher, source_contract, added ORDER BY block_number DESC, log_index DESC) AS rn
    FROM ev
  ),
  a AS (SELECT * FROM r WHERE added = 1 AND rn = 1),
  d AS (SELECT * FROM r WHERE added = 0 AND rn = 1)
  SELECT a.slasher AS slasher_address, a.source_contract,
         NOT (d.slasher IS NOT NULL AND (d.block_number, d.log_index) > (a.block_number, a.log_index)) AS active,
         a.block_number AS added_at_block, to_timestamp(a.block_timestamp) AS added_at,
         CASE WHEN (d.block_number, d.log_index) > (a.block_number, a.log_index) THEN d.block_number END AS removed_at_block,
         CASE WHEN (d.block_number, d.log_index) > (a.block_number, a.log_index) THEN to_timestamp(d.block_timestamp) END AS removed_at
  FROM a LEFT JOIN d ON d.slasher = a.slasher AND d.source_contract = a.source_contract;

-- S5GlobalParams, S5RecidivismParams, S6Params (singletons). Every event sets all of the entity's
-- fields, so each is the latest event's row, and there is none until the first event.
CREATE VIEW s5_global_params AS
  SELECT "window_dec" AS "window", "threshold_dec" AS threshold,
         block_number AS updated_at_block, to_timestamp(block_timestamp) AS updated_at
  FROM (
    SELECT *, ROW_NUMBER() OVER (ORDER BY block_number DESC, log_index DESC) AS rn FROM stake__s5_global_params_updated
  ) p WHERE rn = 1;

CREATE VIEW s5_recidivism_params AS
  SELECT "window_dec" AS "window", "threshold_dec" AS threshold, "jailDuration_dec" AS jail_duration,
         block_number AS updated_at_block, to_timestamp(block_timestamp) AS updated_at
  FROM (
    SELECT *, ROW_NUMBER() OVER (ORDER BY block_number DESC, log_index DESC) AS rn FROM stake__s5_recidivism_params_updated
  ) p WHERE rn = 1;

CREATE VIEW s6_params AS
  SELECT "threshold_dec" AS threshold,
         block_number AS updated_at_block, to_timestamp(block_timestamp) AS updated_at
  FROM (
    SELECT *, ROW_NUMBER() OVER (ORDER BY block_number DESC, log_index DESC) AS rn FROM stake__s6_params_updated
  ) p WHERE rn = 1;

-- UnstakeRequest, one per ValidatorUnstakeRequested. PR 29 writes `claimed = false` and never sets
-- it again, so `claimed` is false on every row here too; it is not derived from
-- ValidatorWithdrawalClaimed. See the README.
CREATE VIEW unstake_requests AS
  SELECT validator, "amount_dec" AS amount, to_timestamp(CAST("withdrawAvailableAt" AS BIGINT)) AS withdraw_available_at,
         false AS claimed, block_number, to_timestamp(block_timestamp) AS requested_at, tx_hash
  FROM stake__validator_unstake_requested;

-- FeeSource, keyed (router, source). Same add/remove rule as slasher_registrations.
CREATE VIEW fee_sources AS
  WITH ev AS (
    SELECT address AS router, source, 1 AS added, block_number, log_index, block_timestamp FROM fee_router__fee_source_added
    UNION ALL SELECT address, source, 0, block_number, log_index, block_timestamp FROM fee_router__fee_source_removed
  ),
  r AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY router, source, added ORDER BY block_number DESC, log_index DESC) AS rn FROM ev
  ),
  a AS (SELECT * FROM r WHERE added = 1 AND rn = 1),
  d AS (SELECT * FROM r WHERE added = 0 AND rn = 1)
  SELECT a.router, a.source,
         NOT (d.source IS NOT NULL AND (d.block_number, d.log_index) > (a.block_number, a.log_index)) AS active,
         a.block_number AS added_at_block, to_timestamp(a.block_timestamp) AS added_at,
         CASE WHEN (d.block_number, d.log_index) > (a.block_number, a.log_index) THEN d.block_number END AS removed_at_block,
         CASE WHEN (d.block_number, d.log_index) > (a.block_number, a.log_index) THEN to_timestamp(d.block_timestamp) END AS removed_at
  FROM a LEFT JOIN d ON d.router = a.router AND d.source = a.source;

-- FeeRouterConfig, one row per router. Each of four events sets some of its fields and leaves the
-- rest as they were, so every column is the latest event that carries it. The two splits are
-- tuples, stored as JSON.
CREATE VIEW fee_router_config AS
  WITH e AS (
    SELECT address AS router, block_number, log_index, block_timestamp, 'treasury' AS k, treasury AS t, CAST(NULL AS BIGINT) AS n
    FROM fee_router__treasury_updated
    UNION ALL
    SELECT address, block_number, log_index, block_timestamp, 'ceiling', NULL, CAST("ceiling" AS BIGINT)
    FROM fee_router__treasury_bps_ceiling_updated
    UNION ALL
    SELECT address, block_number, log_index, block_timestamp, 'din_validator_pool', NULL, CAST(json_extract_string(split, 'validatorPoolBps') AS BIGINT) FROM fee_router__din_split_updated
    UNION ALL
    SELECT address, block_number, log_index, block_timestamp, 'din_treasury', NULL, CAST(json_extract_string(split, 'treasuryBps') AS BIGINT) FROM fee_router__din_split_updated
    UNION ALL
    SELECT address, block_number, log_index, block_timestamp, 'din_burn', NULL, CAST(json_extract_string(split, 'burnBps') AS BIGINT) FROM fee_router__din_split_updated
    UNION ALL
    SELECT address, block_number, log_index, block_timestamp, 'din_storage', NULL, CAST(json_extract_string(split, 'storageBps') AS BIGINT) FROM fee_router__din_split_updated
    UNION ALL
    SELECT address, block_number, log_index, block_timestamp, 'din_public_goods', NULL, CAST(json_extract_string(split, 'publicGoodsBps') AS BIGINT) FROM fee_router__din_split_updated
    UNION ALL
    SELECT address, block_number, log_index, block_timestamp, 'eth_validator_pool', NULL, CAST(json_extract_string(split, 'validatorPoolBps') AS BIGINT) FROM fee_router__eth_split_updated
    UNION ALL
    SELECT address, block_number, log_index, block_timestamp, 'eth_treasury', NULL, CAST(json_extract_string(split, 'treasuryBps') AS BIGINT) FROM fee_router__eth_split_updated
    UNION ALL
    SELECT address, block_number, log_index, block_timestamp, 'eth_storage', NULL, CAST(json_extract_string(split, 'storageBps') AS BIGINT) FROM fee_router__eth_split_updated
    UNION ALL
    SELECT address, block_number, log_index, block_timestamp, 'eth_public_goods', NULL, CAST(json_extract_string(split, 'publicGoodsBps') AS BIGINT) FROM fee_router__eth_split_updated
  ),
  latest AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY router, k ORDER BY block_number DESC, log_index DESC) AS rn FROM e
  )
  SELECT router,
         max(CASE WHEN k = 'treasury' THEN t END) AS treasury,
         max(CASE WHEN k = 'ceiling' THEN n END) AS treasury_bps_ceiling,
         max(CASE WHEN k = 'din_validator_pool' THEN n END) AS din_validator_pool_bps,
         max(CASE WHEN k = 'din_treasury' THEN n END) AS din_treasury_bps,
         max(CASE WHEN k = 'din_burn' THEN n END) AS din_burn_bps,
         max(CASE WHEN k = 'din_storage' THEN n END) AS din_storage_bps,
         max(CASE WHEN k = 'din_public_goods' THEN n END) AS din_public_goods_bps,
         max(CASE WHEN k = 'eth_validator_pool' THEN n END) AS eth_validator_pool_bps,
         max(CASE WHEN k = 'eth_treasury' THEN n END) AS eth_treasury_bps,
         max(CASE WHEN k = 'eth_storage' THEN n END) AS eth_storage_bps,
         max(CASE WHEN k = 'eth_public_goods' THEN n END) AS eth_public_goods_bps,
         max(block_number) AS updated_at_block,
         to_timestamp(max(block_timestamp)) AS updated_at
  FROM latest WHERE rn = 1 GROUP BY router;
