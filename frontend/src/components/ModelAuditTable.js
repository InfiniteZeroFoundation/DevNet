import React from "react";

export default function ModelAuditTable({ submissions, modelAuditData }) {
  // Helper to get votes and batch info for a model by index
  const getAuditInfo = (modelIndex) => {
    return modelAuditData?.find((item) => item.modelIndex === modelIndex) || {
      batchInfo: null,
      votes: []
    };
  };

  const getStatusEmoji = (sub) => {
    if (!sub.evaluated) return "⏳";
    return sub.approved ? "✅" : "❌";
  };

  // Safety checks
  if (!Array.isArray(submissions)) {
    return <p className="text-red-600">❌ No submission data available</p>;
  }

  if (!Array.isArray(modelAuditData)) {
    return <p className="text-orange-600">🟡 Audit data not available yet</p>;
  }

  return (
    <div className="p-4">
      <h2 className="text-2xl font-bold mb-4">🧠 Model Submissions & Audit Results</h2>

      {submissions.length === 0 ? (
        <p className="text-gray-500">No models submitted.</p>
      ) : (
        <div className="space-y-6">
          {submissions.map((sub) => {
            const auditInfo = getAuditInfo(sub.index);
            const { batchInfo, votes } = auditInfo;

            return (
              <div
                key={sub.index}
                style={{
                  marginTop: "1.5rem",
                  marginBottom: "1.5rem",
                  padding: "1rem",
                  border: "1px solid #ccc",
                  borderRadius: "8px",
                  maxWidth: "600px",
                  marginInline: "auto",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.1)",
                  fontFamily: "sans-serif"
                }}
              >
                {/* Model Header */}
                <div style={{ marginBottom: "1rem" }}>
                  <h3 className="font-bold text-lg">
                    {getStatusEmoji(sub)} Model #{sub.index}
                  </h3>
                  <p>
                    <strong>Client:</strong>{" "}
                    {sub.client?.slice(0, 6)}...{sub.client?.slice(-4)}
                  </p>
                  <p>
                    <strong>CID:</strong>{" "}
                    <code
                      style={{
                        backgroundColor: "#f1f1f1",
                        padding: "2px 4px",
                        borderRadius: "4px",
                        fontSize: "0.9em"
                      }}
                    >
                      {sub.modelCID}
                    </code>
                  </p>
                </div>

                {/* Final Status */}
                <div
                  style={{
                    padding: "0.75rem",
                    backgroundColor: sub.evaluated
                      ? sub.approved
                        ? "#d4edda"
                        : "#f8d7da"
                      : "#fff3cd",
                    border: `1px solid ${
                      sub.approved ? "#c3e6cb" : sub.evaluated ? "#f5c6cb" : "#ffeaa7"
                    }`,
                    borderRadius: "6px",
                    marginBottom: "1rem"
                  }}
                >
                  <strong>Status:</strong>{" "}
                  {sub.evaluated ? (
                    sub.approved ? (
                      <span style={{ color: "green" }}>✅ Approved</span>
                    ) : (
                      <span style={{ color: "red" }}>❌ Rejected</span>
                    )
                  ) : (
                    <span style={{ color: "#856404" }}>⏳ Pending Evaluation</span>
                  )}
                  {sub.evaluated && (
                    <span style={{ marginLeft: "1rem" }}>
                      <strong>Avg Score:</strong> {sub.finalAvgScore}/100
                    </span>
                  )}
                </div>

                {/* Audit Details */}
                <div style={{ fontSize: "0.95rem" }}>
                  <h4 style={{ margin: "0.5rem 0", fontWeight: "bold" }}>
                    📋 Audit Batch Info
                  </h4>
                  {batchInfo ? (
                    <ul style={{ listStyle: "none", padding: 0, margin: "0.5rem 0" }}>
                      <li>
                        <strong>Batch ID:</strong> {batchInfo.batch_id}
                      </li>
                      <li>
                        <strong>Test CID:</strong>{" "}
                        <code
                          style={{
                            backgroundColor: "#e9ecef",
                            padding: "2px 4px",
                            borderRadius: "4px",
                            wordBreak: "break-all"
                          }}
                        >
                          {batchInfo.test_cid}
                        </code>
                      </li>
                    </ul>
                  ) : (
                    <p style={{ color: "orange", fontStyle: "italic" }}>
                      ⚠️ Not assigned to any audit batch
                    </p>
                  )}

                  {/* Auditor Votes Table */}
                  <h4 style={{ margin: "1rem 0 0.5rem", fontWeight: "bold" }}>
                    🗳️ Auditor Votes
                  </h4>
                  {votes.length === 0 ? (
                    <p style={{ color: "#6c757d", fontSize: "0.9em" }}>
                      No auditors assigned.
                    </p>
                  ) : (
                    <table
                      style={{
                        width: "100%",
                        borderCollapse: "collapse",
                        fontSize: "0.85rem"
                      }}
                    >
                      <thead>
                        <tr style={{ backgroundColor: "#f8f9fa" }}>
                          <th
                            style={{
                              textAlign: "left",
                              padding: "6px",
                              border: "1px solid #ddd"
                            }}
                          >
                            Auditor
                          </th>
                          <th
                            style={{
                              textAlign: "center",
                              padding: "6px",
                              border: "1px solid #ddd"
                            }}
                          >
                            Voted
                          </th>
                          <th
                            style={{
                              textAlign: "center",
                              padding: "6px",
                              border: "1px solid #ddd"
                            }}
                          >
                            Score
                          </th>
                          <th
                            style={{
                              textAlign: "center",
                              padding: "6px",
                              border: "1px solid #ddd"
                            }}
                          >
                            Eligible
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {votes.map((v, idx) => (
                          <tr key={idx} style={{ borderBottom: "1px solid #eee" }}>
                            <td
                              style={{
                                padding: "6px",
                                fontFamily: "monospace",
                                fontSize: "0.8em"
                              }}
                            >
                              {v.auditorShort}
                            </td>
                            <td
                              style={{
                                textAlign: "center",
                                padding: "6px",
                                color: v.hasVoted ? "green" : "gray"
                              }}
                            >
                              {v.hasVoted ? "✅" : "⚪"}
                            </td>
                            <td
                              style={{
                                textAlign: "center",
                                padding: "6px",
                                fontWeight: v.hasVoted ? "bold" : "normal",
                                color: v.hasVoted && v.score >= 50 ? "green" : v.hasVoted ? "red" : "gray"
                              }}
                            >
                              {v.hasVoted ? v.score : "–"}
                            </td>
                            <td
                              style={{
                                textAlign: "center",
                                padding: "6px"
                              }}
                            >
                              {v.hasVoted ? (v.eligible ? "✅" : "❌") : "–"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}