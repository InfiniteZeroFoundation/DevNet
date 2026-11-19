-- Each model as approved, with its latest kill-switch state. Owner comes from the registration
-- request; the task contract addresses need registry.getModel(), see the README.
CREATE VIEW models AS
  WITH switch AS (
    SELECT "modelId", disabled, ROW_NUMBER() OVER (PARTITION BY "modelId" ORDER BY _seq DESC) AS rn
    FROM (
      SELECT "modelId", _seq, true AS disabled FROM registry__model_disabled
      UNION ALL SELECT "modelId", _seq, false FROM registry__model_enabled
    ) s
  )
  SELECT a."modelId_dec" AS model_id,
         r.requester AS owner,
         a."requestId_dec" AS request_id,
         to_timestamp(a.block_timestamp) AS approved_at,
         coalesce(s.disabled, false) AS disabled
  FROM registry__model_approved a
  JOIN registry__model_registration_requested r ON r."requestId" = a."requestId"
  LEFT JOIN switch s ON s."modelId" = a."modelId" AND s.rn = 1;

-- One row per validator: running totals, and active stake with slashes floored at zero. The
-- subgraph clamps step by step; the closed form is the final sum less its lowest negative point.
CREATE VIEW validators AS
  WITH moves AS (
    SELECT validator, _seq, CAST(amount AS DECIMAL(38, 0)) AS staked, 0 AS slashed, 0 AS unstaked FROM stake__validator_staked
    UNION ALL SELECT validator, _seq, 0, CAST(amount AS DECIMAL(38, 0)), 0 FROM stake__validator_slashed
    UNION ALL SELECT validator, _seq, 0, 0, CAST(amount AS DECIMAL(38, 0)) FROM stake__validator_unstake_requested
  ),
  running AS (
    SELECT validator, staked, slashed, unstaked,
           sum(staked - slashed - unstaked) OVER (PARTITION BY validator ORDER BY _seq) AS raw
    FROM moves
  ),
  flags AS (
    SELECT validator, grp, on_ AS flag,
           ROW_NUMBER() OVER (PARTITION BY validator, grp ORDER BY _seq DESC) AS rn
    FROM (
      SELECT validator, _seq, 'blacklist' AS grp, 1 AS on_ FROM stake__validator_blacklisted
      UNION ALL SELECT validator, _seq, 'blacklist', 0 FROM stake__validator_unblacklisted
      UNION ALL SELECT validator, _seq, 'jail', 1 FROM stake__validator_jailed
      UNION ALL SELECT validator, _seq, 'jail', 0 FROM stake__validator_reactivated
    ) f
  ),
  latest AS (
    SELECT validator,
           max(CASE WHEN grp = 'blacklist' THEN flag ELSE 0 END) AS blacklisted,
           max(CASE WHEN grp = 'jail' THEN flag ELSE 0 END) AS jailed
    FROM flags WHERE rn = 1 GROUP BY validator
  ),
  withdrawn AS (
    SELECT validator, sum(CAST(amount AS DECIMAL(38, 0))) AS total_withdrawn FROM stake__validator_withdrawal_claimed GROUP BY validator
  ),
  -- the subgraph adds one per increment and takes one per decrement but never below zero, so the
  -- count is the final sum less its lowest negative point, as with active stake above
  regs AS (
    SELECT validator, sum(d) - least(0, min(raw)) AS active_registrations
    FROM (
      SELECT validator, d, sum(d) OVER (PARTITION BY validator ORDER BY block_number, log_index) AS raw
      FROM (
        SELECT validator, block_number, log_index, 1 AS d FROM stake__active_registration_incremented
        UNION ALL SELECT validator, block_number, log_index, -1 FROM stake__active_registration_decremented
      ) m
    ) x GROUP BY validator
  ),
  enc AS (
    SELECT validator, pubkey FROM (
      SELECT validator, pubkey, ROW_NUMBER() OVER (PARTITION BY validator ORDER BY block_number DESC, log_index DESC) AS rn
      FROM stake__encryption_key_registered
    ) k WHERE rn = 1
  ),
  jail AS (
    SELECT validator, CASE WHEN until IS NOT NULL THEN CAST(until AS BIGINT) END AS jailed_until FROM (
      SELECT validator, until, ROW_NUMBER() OVER (PARTITION BY validator ORDER BY block_number DESC, log_index DESC) AS rn
      FROM (
        SELECT validator, "jailedUntil" AS until, block_number, log_index FROM stake__validator_jailed
        UNION ALL SELECT validator, CAST(NULL AS VARCHAR), block_number, log_index FROM stake__validator_reactivated
      ) j
    ) k WHERE rn = 1
  )
  SELECT r.validator,
         sum(r.staked) AS total_staked,
         sum(r.slashed) AS total_slashed,
         sum(r.unstaked) AS total_unstake_requested,
         sum(r.staked - r.slashed - r.unstaked) - least(0, min(r.raw)) AS active_stake,
         coalesce(max(l.blacklisted), 0) = 1 AS blacklisted,
         coalesce(max(l.jailed), 0) = 1 AS jailed,
         max(jail.jailed_until) AS jailed_until,
         coalesce(max(withdrawn.total_withdrawn), CAST(0 AS DECIMAL(38, 0))) AS total_withdrawn,
         coalesce(max(regs.active_registrations), 0) AS active_registrations,
         max(enc.pubkey) AS encryption_key
  FROM running r
  LEFT JOIN latest l ON l.validator = r.validator
  LEFT JOIN jail ON jail.validator = r.validator
  LEFT JOIN withdrawn ON withdrawn.validator = r.validator
  LEFT JOIN regs ON regs.validator = r.validator
  LEFT JOIN enc ON enc.validator = r.validator
  GROUP BY r.validator;

-- Each global iteration per task coordinator, its current state and when it started.
CREATE VIEW global_iterations AS
  WITH s AS (
    SELECT address AS task_coordinator, "GI_dec" AS gi, "newState" AS state, block_timestamp,
           ROW_NUMBER() OVER (PARTITION BY address, "GI" ORDER BY _seq DESC) AS rn,
           min(block_timestamp) OVER (PARTITION BY address, "GI") AS first_ts
    FROM task__g_i_state_changed
    WHERE "GI_dec" > 0
  )
  SELECT task_coordinator, gi, state AS current_state, to_timestamp(first_ts) AS started_at,
         state = 28 AS ended
  FROM s WHERE rn = 1;

-- Aggregators and auditors registered per iteration, from either task contract.
CREATE VIEW registrations AS
  SELECT address AS task_contract, 'aggregator' AS role, "GI_dec" AS gi, validator AS account,
         to_timestamp(block_timestamp) AS registered_at
  FROM task__d_i_n_validator_registered
  UNION ALL
  SELECT address, 'auditor', "GI_dec", auditor, to_timestamp(block_timestamp)
  FROM task__d_i_n_auditor_registered;

-- Which task contracts belong to which model, sliced from getModel()'s return: a static struct of
-- owner, isOpenSource, manifestCID, createdAt, taskCoordinator, taskAuditor, one word each.
CREATE VIEW model_contracts AS
  SELECT a."modelId_dec" AS model_id,
         '0x' || substr(c.result, 3 + 64 * 4 + 24, 40) AS task_coordinator,
         '0x' || substr(c.result, 3 + 64 * 5 + 24, 40) AS task_auditor,
         '0x' || substr(c.result, 3 + 64 * 2, 64) AS manifest_cid,
         substr(c.result, 3 + 64 * 2 - 1, 1) = '1' AS is_open_source
  FROM registry__model_approved a
  JOIN model_record c ON c.block_number = a.block_number
   AND substr(c.calldata, 11) = lpad(to_hex(CAST(a."modelId_dec" AS BIGINT)), 64, '0');
