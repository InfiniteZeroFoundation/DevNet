import sys


def u256(w):
    """SQL expression: the 32 low hex digits of word `w` (a 64-char hex string) as DECIMAL(38,0)."""
    terms=[]
    for i in range(32):
        terms.append(f"(strpos('0123456789abcdef', substr({w}, {33 + i}, 1)) - 1) * CAST('{16 ** (31 - i)}' AS DECIMAL(38, 0))")
    return "CAST(" + " + ".join(terms) + " AS DECIMAL(38, 0))"
def word(col, n):  # nth 32-byte word of a 0x result, as 64 hex chars
    return f"substr({col}, {3 + 64 * n}, 64)"
def addr(col, n):
    return f"'0x' || substr({col}, {3 + 64 * n + 24}, 40)"
def flag(col, n):
    return f"substr({col}, {3 + 64 * n + 63}, 1) = '1'"
out=[]
out.append("""-- The registry reads the subgraph makes with `contract.method(...)` inside a handler. Each is a
-- row-driven [[calls]] in nuthatch.toml, pinned to the block of the event that triggers it, and each
-- result is the raw ABI return in `result`, one 32-byte word per field. The views slice the words.
-- A uint256 word is turned into DECIMAL(38,0) from its low 32 hex digits (the high 32 are zero for
-- any fee that fits in 38 digits). Its expression is written out in full because the SQL surface
-- has no hex-to-number function; spike/gen-reads.py wrote it.

-- ModelRegistrationRequest: modelRequests(requestId) at the request's block, then ModelApproved or
-- ModelRejected marks it processed. `model_id` is set only on approval, as in the subgraph.
CREATE VIEW model_registration_requests AS
  WITH p AS (
    SELECT "requestId", 'approved' AS how, block_number, block_timestamp, log_index, "modelId_dec" AS model_id FROM registry__model_approved
    UNION ALL
    SELECT "requestId", 'rejected', block_number, block_timestamp, log_index, CAST(NULL AS DECIMAL(38, 0)) FROM registry__model_rejected
  ),
  lp AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY "requestId" ORDER BY block_number DESC, log_index DESC) AS rn FROM p
  )
  SELECT r."requestId_dec" AS request_id, r.requester,
         %s AS is_open_source,
         %s AS fee_paid,
         '0x' || %s AS manifest_cid,
         %s AS task_coordinator,
         %s AS task_auditor,
         lp.how IS NOT NULL AS processed,
         CASE WHEN lp.how IS NOT NULL THEN lp.how = 'approved' END AS approved,
         lp.model_id,
         r.block_number AS submitted_at_block, to_timestamp(r.block_timestamp) AS submitted_at,
         lp.block_number AS processed_at_block, to_timestamp(lp.block_timestamp) AS processed_at
  FROM registry__model_registration_requested r
  JOIN model_request_record c ON c.block_number = r.block_number
   AND substr(c.calldata, 11) = lpad(to_hex(CAST(r."requestId_dec" AS BIGINT)), 64, '0')
  LEFT JOIN lp ON lp.rn = 1 AND lp."requestId" = r."requestId";
""" % (flag("c.result",1), u256(word("c.result",5)), word("c.result",2), addr("c.result",3), addr("c.result",4)))
out.append("""
-- ManifestUpdateRequest: manifestRequests(requestId) at the request's block, then ManifestUpdated
-- or ManifestUpdateRejected marks it processed. The requester is the model's owner when the model
-- is known (only its owner can ask), else the transaction's sender, which this nest does not keep,
-- so it is NULL then.
CREATE VIEW manifest_update_requests AS
  WITH p AS (
    SELECT "requestId", 'approved' AS how, block_number, block_timestamp, log_index FROM registry__manifest_updated
    UNION ALL
    SELECT "requestId", 'rejected', block_number, block_timestamp, log_index FROM registry__manifest_update_rejected
  ),
  lp AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY "requestId" ORDER BY block_number DESC, log_index DESC) AS rn FROM p
  )
  SELECT r."requestId_dec" AS request_id, r."modelId_dec" AS model_id, m.owner AS requester,
         %s AS fee_paid,
         '0x' || %s AS new_manifest_cid,
         lp.how IS NOT NULL AS processed,
         CASE WHEN lp.how IS NOT NULL THEN lp.how = 'approved' END AS approved,
         r.block_number AS submitted_at_block, to_timestamp(r.block_timestamp) AS submitted_at,
         lp.block_number AS processed_at_block, to_timestamp(lp.block_timestamp) AS processed_at
  FROM registry__manifest_update_requested r
  JOIN manifest_request_record c ON c.block_number = r.block_number
   AND substr(c.calldata, 11) = lpad(to_hex(CAST(r."requestId_dec" AS BIGINT)), 64, '0')
  LEFT JOIN models m ON m.model_id = r."modelId_dec"
  LEFT JOIN lp ON lp.rn = 1 AND lp."requestId" = r."requestId";
""" % (u256(word("c.result",3)), word("c.result",1)))
out.append("""
-- FeeSnapshot. The four single setters carry only their own new value, so the whole schedule comes
-- from the four getters, read at the event's block ("granular"; one table of calls per getter per
-- setter, fee_<getter>_on_<event>). FeesUpdated carries all four ("atomic").
CREATE VIEW fee_snapshots AS
""" + "\n  UNION ALL\n".join(
"""  SELECT %s AS open_source_fee, %s AS proprietary_fee,
         %s AS open_source_update_fee, %s AS proprietary_update_fee,
         'granular' AS update_kind, g.block_number, to_timestamp(g.block_timestamp) AS at, g.tx_hash, g.log_index
  FROM registry__%s_updated g
  JOIN fee_os_on_%s a ON a.block_number = g.block_number
  JOIN fee_pr_on_%s b ON b.block_number = g.block_number
  JOIN fee_osu_on_%s c ON c.block_number = g.block_number
  JOIN fee_pru_on_%s d ON d.block_number = g.block_number""" % (u256("substr(a.result, 3, 64)"), u256("substr(b.result, 3, 64)"), u256("substr(c.result, 3, 64)"), u256("substr(d.result, 3, 64)"), e, e, e, e, e)
for e in ["open_source_fee","proprietary_fee","open_source_update_fee","proprietary_update_fee"]) + """
  UNION ALL
  SELECT "openSourceFee_dec", "proprietaryFee_dec", "openSourceUpdateFee_dec", "proprietaryUpdateFee_dec",
         'atomic', block_number, to_timestamp(block_timestamp), tx_hash, log_index
  FROM registry__fees_updated;
""")
out.append("""
-- RegistryFeeWithdrawal: a sweep to the router, whose address the event does not carry, so it is
-- read with feeRouter() at the sweep's block. A reverted read gives the zero address, as in the subgraph.
CREATE VIEW registry_fee_withdrawals AS
  SELECT CASE WHEN c.reverted = 'true' OR c.result IS NULL THEN '0x0000000000000000000000000000000000000000'
              ELSE %s END AS "to",
         s."amount_dec" AS amount, s.block_number, to_timestamp(s.block_timestamp) AS at, s.tx_hash
  FROM registry__fees_swept_to_router s
  LEFT JOIN registry_fee_router_record c ON c.block_number = s.block_number;
""" % addr("c.result", 0))
out.append("""
-- Model.manifestCID as the subgraph keeps it: set from getModel() at approval (model_contracts),
-- then replaced by each ManifestUpdated. `models` and `model_contracts` carry the approval-time CID.
CREATE VIEW current_manifests AS
  SELECT mc.model_id,
         coalesce(u.new_cid, mc.manifest_cid) AS manifest_cid,
         u.block_number IS NOT NULL AS updated
  FROM model_contracts mc
  LEFT JOIN (
    SELECT "modelId_dec" AS model_id, "newCID" AS new_cid, block_number,
           ROW_NUMBER() OVER (PARTITION BY "modelId" ORDER BY block_number DESC, log_index DESC) AS rn
    FROM registry__manifest_updated
  ) u ON u.rn = 1 AND u.model_id = mc.model_id;
""")
open(sys.argv[1],'w').write("".join(out))
