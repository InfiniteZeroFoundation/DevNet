-- The task contracts' view-shaped entities from PR 29's schema.graphql (613f5b2). A task row's key
-- starts with the address of the contract that emitted it (`address`): the coordinator's rows are
-- keyed by `task_coordinator`, the auditor's by `task_auditor`. model_contracts pairs the two.
-- The subgraph writes an entity with `new X(id)` and `save()`, so a second event with the same id
-- replaces the first: each of these is the latest row per key, ordered by (block_number, log_index).
-- Small integers (uint8, uint16, uint64) are text in the tables, so they are cast here; bools are
-- the text 'true' / 'false'.

-- GIStateTransition, one per (coordinator, GI, state entered).
CREATE VIEW gi_state_transitions AS
  SELECT address AS task_coordinator, gi, new_state, block_number, to_timestamp(block_timestamp) AS at, tx_hash
  FROM (
    SELECT address, "GI_dec" AS gi, CAST("newState" AS BIGINT) AS new_state, block_number, block_timestamp, tx_hash,
           ROW_NUMBER() OVER (PARTITION BY address, "GI", "newState" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__g_i_state_changed
  ) t WHERE rn = 1;

-- Tier1Batch: created by Tier1BatchAuto, finished by T1BatchFinalized.
CREATE VIEW tier1_batches AS
  WITH c AS (
    SELECT address, "GI", "batchId", block_number, block_timestamp,
           ROW_NUMBER() OVER (PARTITION BY address, "GI", "batchId" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__tier1_batch_auto
  ),
  f AS (
    SELECT address, "GI", "batchId", "winningCID", block_number, block_timestamp,
           ROW_NUMBER() OVER (PARTITION BY address, "GI", "batchId" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__t1_batch_finalized
  )
  SELECT c.address AS task_coordinator, CAST(c."GI" AS DECIMAL(38, 0)) AS gi, CAST(c."batchId" AS DECIMAL(38, 0)) AS batch_id,
         f.address IS NOT NULL AS finalized, f."winningCID" AS winning_cid,
         c.block_number AS created_at_block, to_timestamp(c.block_timestamp) AS created_at,
         f.block_number AS finalized_at_block, to_timestamp(f.block_timestamp) AS finalized_at
  FROM c LEFT JOIN f ON f.rn = 1 AND f.address = c.address AND f."GI" = c."GI" AND f."batchId" = c."batchId"
  WHERE c.rn = 1;

-- Tier2Batch: one per (coordinator, GI), its batchId is always 0. T2Finalized finishes it.
CREATE VIEW tier2_batches AS
  WITH c AS (
    SELECT address, "GI", block_number, block_timestamp,
           ROW_NUMBER() OVER (PARTITION BY address, "GI" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__tier2_batch_auto
  ),
  f AS (
    SELECT address, "GI", "globalModelCID", block_number, block_timestamp,
           ROW_NUMBER() OVER (PARTITION BY address, "GI" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__t2_finalized
  )
  SELECT c.address AS task_coordinator, CAST(c."GI" AS DECIMAL(38, 0)) AS gi,
         f.address IS NOT NULL AS finalized, f."globalModelCID" AS global_model_cid,
         c.block_number AS created_at_block, to_timestamp(c.block_timestamp) AS created_at,
         f.block_number AS finalized_at_block, to_timestamp(f.block_timestamp) AS finalized_at
  FROM c LEFT JOIN f ON f.rn = 1 AND f.address = c.address AND f."GI" = c."GI"
  WHERE c.rn = 1;

-- T1AggregationSubmission, T2AggregationSubmission: one per (batch, aggregator).
CREATE VIEW t1_aggregation_submissions AS
  SELECT address AS task_coordinator, "GI_dec" AS gi, "batchId_dec" AS batch_id, aggregator, cid,
         block_number, to_timestamp(block_timestamp) AS at, tx_hash
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, "GI", "batchId", aggregator ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__t1_aggregation_submitted
  ) t WHERE rn = 1;

CREATE VIEW t2_aggregation_submissions AS
  SELECT address AS task_coordinator, "GI_dec" AS gi, aggregator, cid,
         block_number, to_timestamp(block_timestamp) AS at, tx_hash
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, "GI", aggregator ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__t2_aggregation_submitted
  ) t WHERE rn = 1;

-- T1AggregationCommitment, T2AggregationCommitment.
CREATE VIEW t1_aggregation_commitments AS
  SELECT address AS task_coordinator, "GI_dec" AS gi, "batchId_dec" AS batch_id, aggregator, "commitHash" AS commit_hash,
         block_number, to_timestamp(block_timestamp) AS at, tx_hash
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, "GI", "batchId", aggregator ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__t1_aggregation_committed
  ) t WHERE rn = 1;

CREATE VIEW t2_aggregation_commitments AS
  SELECT address AS task_coordinator, "GI_dec" AS gi, aggregator, "commitHash" AS commit_hash,
         block_number, to_timestamp(block_timestamp) AS at, tx_hash
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, "GI", aggregator ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__t2_aggregation_committed
  ) t WHERE rn = 1;

-- SeedLock: ids are (coordinator, GI, "Audit"), (.., "Agg") and (.., "Dispute", tierKind, batchId).
-- A lock sets the seed; a reanchor sets reanchored_at_block and, as in the subgraph, also moves the
-- row's block, timestamp and transaction to the reanchor's.
CREATE VIEW seed_locks AS
  WITH ev AS (
    SELECT address, "GI" AS gi, 'Audit' AS kind, CAST(NULL AS BIGINT) AS tier_kind, CAST(NULL AS VARCHAR) AS batch_id,
           seed, CAST(NULL AS BIGINT) AS new_seed_block, 0 AS is_re, block_number, log_index, block_timestamp, tx_hash
    FROM task__audit_seed_locked
    UNION ALL
    SELECT address, "GI", 'Agg', CAST(NULL AS BIGINT), CAST(NULL AS VARCHAR), seed, CAST(NULL AS BIGINT), 0, block_number, log_index, block_timestamp, tx_hash
    FROM task__agg_seed_locked
    UNION ALL
    SELECT address, "GI", 'Dispute', CAST("tierKind" AS BIGINT), "batchId", seed, CAST(NULL AS BIGINT), 0, block_number, log_index, block_timestamp, tx_hash
    FROM task__dispute_seed_locked
    UNION ALL
    SELECT address, "GI", 'Audit', CAST(NULL AS BIGINT), CAST(NULL AS VARCHAR), CAST(NULL AS VARCHAR), CAST("newSeedBlock" AS BIGINT), 1, block_number, log_index, block_timestamp, tx_hash
    FROM task__audit_seed_reanchored
    UNION ALL
    SELECT address, "GI", 'Agg', CAST(NULL AS BIGINT), CAST(NULL AS VARCHAR), CAST(NULL AS VARCHAR), CAST("newSeedBlock" AS BIGINT), 1, block_number, log_index, block_timestamp, tx_hash
    FROM task__agg_seed_reanchored
    UNION ALL
    SELECT address, "GI", 'Dispute', CAST("tierKind" AS BIGINT), "batchId", CAST(NULL AS VARCHAR), CAST("newSeedBlock" AS BIGINT), 1, block_number, log_index, block_timestamp, tx_hash
    FROM task__dispute_seed_reanchored
  ),
  r AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY address, gi, kind, tier_kind, batch_id, is_re ORDER BY block_number DESC, log_index DESC) AS rn_kind,
           ROW_NUMBER() OVER (PARTITION BY address, gi, kind, tier_kind, batch_id ORDER BY block_number DESC, log_index DESC) AS rn_any
    FROM ev
  )
  SELECT address AS task_coordinator, CAST(gi AS DECIMAL(38, 0)) AS gi, kind, tier_kind,
         CAST(batch_id AS DECIMAL(38, 0)) AS batch_id,
         max(CASE WHEN is_re = 0 AND rn_kind = 1 THEN seed END) AS seed,
         max(CASE WHEN is_re = 1 AND rn_kind = 1 THEN new_seed_block END) AS reanchored_at_block,
         max(CASE WHEN rn_any = 1 THEN block_number END) AS block_number,
         to_timestamp(max(CASE WHEN rn_any = 1 THEN block_timestamp END)) AS at,
         max(CASE WHEN rn_any = 1 THEN tx_hash END) AS tx_hash
  FROM r GROUP BY address, gi, kind, tier_kind, batch_id;

-- TaskCoordinatorGovernance: the coordinator's S2 slash fraction.
CREATE VIEW task_coordinator_governance AS
  SELECT address AS task_coordinator, "newBps_dec" AS s2_slash_fraction_bps,
         block_number AS updated_at_block, to_timestamp(block_timestamp) AS updated_at
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__s2_slash_fraction_bps_updated
  ) t WHERE rn = 1;

-- TaskAuditorGovernance: three settings, each moved by its own event; updated_at is the last of them.
CREATE VIEW task_auditor_governance AS
  WITH e AS (
    SELECT address, block_number, log_index, block_timestamp, 's1' AS k, "newBps" AS v FROM task__s1_slash_fraction_bps_updated
    UNION ALL SELECT address, block_number, log_index, block_timestamp, 's3_threshold', "newThreshold" FROM task__s3_deviation_threshold_updated
    UNION ALL SELECT address, block_number, log_index, block_timestamp, 's3_enabled', "newValue" FROM task__s3_slashing_enabled_updated
  ),
  l AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, k ORDER BY block_number DESC, log_index DESC) AS rn FROM e
  )
  SELECT address AS task_auditor,
         CAST(max(CASE WHEN k = 's1' THEN v END) AS DECIMAL(38, 0)) AS s1_slash_fraction_bps,
         CAST(max(CASE WHEN k = 's3_threshold' THEN v END) AS DECIMAL(38, 0)) AS s3_deviation_threshold,
         max(CASE WHEN k = 's3_enabled' THEN v END) = 'true' AS s3_slashing_enabled,
         max(block_number) AS updated_at_block, to_timestamp(max(block_timestamp)) AS updated_at
  FROM l WHERE rn = 1 GROUP BY address;

-- RewardSplit: the latest split per auditor contract. The split is a tuple, stored as JSON.
CREATE VIEW reward_splits AS
  SELECT address AS task_auditor,
         CAST(json_extract_string(split, 'clientBps') AS BIGINT) AS client_bps,
         CAST(json_extract_string(split, 'auditorBps') AS BIGINT) AS auditor_bps,
         CAST(json_extract_string(split, 'aggregatorBps') AS BIGINT) AS aggregator_bps,
         CAST(json_extract_string(split, 'treasuryBps') AS BIGINT) AS treasury_bps,
         block_number AS updated_at_block, to_timestamp(block_timestamp) AS updated_at
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__reward_split_updated
  ) t WHERE rn = 1;

-- LocalModelSubmission, keyed (auditor, GI, modelIndex): the client and CID, and `eligible` from the
-- latest EligibilityFinalized for that model index (any batch), NULL until there is one.
CREATE VIEW local_model_submissions AS
  WITH s AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, "GI", "modelIndex" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__local_model_submitted
  ),
  e AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, gi, "modelIndex" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__eligibility_finalized
  )
  SELECT s.address AS task_auditor, s."GI_dec" AS gi, s."modelIndex_dec" AS model_index, s.client, s."modelCID" AS model_cid,
         e.eligible = 'true' AS eligible
  FROM s LEFT JOIN e ON e.rn = 1 AND e.address = s.address AND e.gi = s."GI" AND e."modelIndex" = s."modelIndex"
  WHERE s.rn = 1;

-- AuditBatch, keyed (auditor, GI, batchId). The subgraph creates it the first time any event names
-- the batch, and BatchPendingReassignment sets the flag for good.
CREATE VIEW audit_batches AS
  WITH k AS (
    SELECT address, "GI" AS gi, "batchId", false AS pending FROM task__auditors_batch_auto
    UNION ALL SELECT address, gi, "batchId", false FROM task__audit_score_committed
    UNION ALL SELECT address, gi, "batchId", false FROM task__audit_score_submitted
    UNION ALL SELECT address, gi, "batchId", false FROM task__eligibility_voted
    UNION ALL SELECT address, gi, "batchId", false FROM task__eligibility_finalized
    UNION ALL SELECT address, gi, "batchId", false FROM task__auditor_slashed
    UNION ALL SELECT address, gi, "batchId", false FROM task__test_data_commitment_stored
    UNION ALL SELECT address, gi, "batchId", false FROM task__encrypted_test_data_keys_assigned
    UNION ALL SELECT address, gi, "batchId", false FROM task__test_data_dispute_opened
    UNION ALL SELECT address, gi, "batchId", false FROM task__auditor_score_deviation
    UNION ALL SELECT address, gi, "batchId", true FROM task__batch_pending_reassignment
  )
  SELECT address AS task_auditor, CAST(gi AS DECIMAL(38, 0)) AS gi, CAST("batchId" AS DECIMAL(38, 0)) AS batch_id,
         bool_or(pending) AS pending_reassignment
  FROM k GROUP BY address, gi, "batchId";

-- AuditScoreCommitment, keyed (auditor, GI, batch, auditor account, model index). AuditScoreSubmitted
-- is the reveal: it marks the commitment revealed and records the score. As in the subgraph, a
-- commitment needs its LocalModelSubmission to exist.
CREATE VIEW audit_score_commitments AS
  WITH c AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, gi, "batchId", auditor, "modelIndex" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__audit_score_committed
  ),
  s AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, gi, "batchId", auditor, "modelIndex" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__audit_score_submitted
  )
  SELECT c.address AS task_auditor, c."gi_dec" AS gi, c."batchId_dec" AS batch_id, c.auditor, c."modelIndex_dec" AS model_index,
         c."commitHash" AS commit_hash, s.address IS NOT NULL AS revealed, s."score_dec" AS score,
         s.block_number AS revealed_at_block, to_timestamp(s.block_timestamp) AS revealed_at
  FROM c
  LEFT JOIN s ON s.rn = 1 AND s.address = c.address AND s.gi = c.gi AND s."batchId" = c."batchId" AND s.auditor = c.auditor AND s."modelIndex" = c."modelIndex"
  WHERE c.rn = 1
    AND EXISTS (SELECT 1 FROM task__local_model_submitted m WHERE m.address = c.address AND m."GI" = c.gi AND m."modelIndex" = c."modelIndex");

-- AuditScoreSubmission, same key and the same requirement; `committed` says a commitment was there.
CREATE VIEW audit_score_submissions AS
  WITH s AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, gi, "batchId", auditor, "modelIndex" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__audit_score_submitted
  )
  SELECT s.address AS task_auditor, s."gi_dec" AS gi, s."batchId_dec" AS batch_id, s.auditor, s."modelIndex_dec" AS model_index,
         s."score_dec" AS score,
         EXISTS (SELECT 1 FROM task__audit_score_committed c
                 WHERE c.address = s.address AND c.gi = s.gi AND c."batchId" = s."batchId" AND c.auditor = s.auditor AND c."modelIndex" = s."modelIndex") AS committed,
         s.block_number, to_timestamp(s.block_timestamp) AS at, s.tx_hash
  FROM s
  WHERE s.rn = 1
    AND EXISTS (SELECT 1 FROM task__local_model_submitted m WHERE m.address = s.address AND m."GI" = s.gi AND m."modelIndex" = s."modelIndex");

-- EligibilityVote, keyed (auditor, GI, batch, model index, auditor account). Needs the submission.
CREATE VIEW eligibility_votes AS
  SELECT address AS task_auditor, "gi_dec" AS gi, "batchId_dec" AS batch_id, "modelIndex_dec" AS model_index, auditor,
         vote = 'true' AS vote, block_number, to_timestamp(block_timestamp) AS at, tx_hash
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, gi, "batchId", "modelIndex", auditor ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__eligibility_voted
  ) v
  WHERE rn = 1
    AND EXISTS (SELECT 1 FROM task__local_model_submitted m WHERE m.address = v.address AND m."GI" = v.gi AND m."modelIndex" = v."modelIndex");

-- EligibilityResult, keyed (auditor, GI, batch, model index).
CREATE VIEW eligibility_results AS
  SELECT address AS task_auditor, "gi_dec" AS gi, "batchId_dec" AS batch_id, "modelIndex_dec" AS model_index,
         eligible = 'true' AS eligible, "totalVotes_dec" AS total_votes,
         block_number, to_timestamp(block_timestamp) AS at, tx_hash
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, gi, "batchId", "modelIndex" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__eligibility_finalized
  ) v
  WHERE rn = 1
    AND EXISTS (SELECT 1 FROM task__local_model_submitted m WHERE m.address = v.address AND m."GI" = v.gi AND m."modelIndex" = v."modelIndex");

-- TestDataCommitment, EncryptedTestDataKeys: one per (auditor, GI, batch).
CREATE VIEW test_data_commitments AS
  SELECT address AS task_auditor, "gi_dec" AS gi, "batchId_dec" AS batch_id, commitment,
         block_number, to_timestamp(block_timestamp) AS at, tx_hash
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, gi, "batchId" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__test_data_commitment_stored
  ) t WHERE rn = 1;

CREATE VIEW encrypted_test_data_keys AS
  SELECT address AS task_auditor, "gi_dec" AS gi, "batchId_dec" AS batch_id, "testDataCID" AS test_data_cid,
         "auditorCount_dec" AS auditor_count, block_number, to_timestamp(block_timestamp) AS at, tx_hash
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY address, gi, "batchId" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM task__encrypted_test_data_keys_assigned
  ) t WHERE rn = 1;
