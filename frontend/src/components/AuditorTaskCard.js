// AuditorTaskCard.js
import React from 'react';

export default function AuditorTaskCard({ auditorData, fetchAuditorEvaluationBatches }) {
  const { auditor, assignedModels } = auditorData;


  const handleEvaluate = async (task, auditor) => {
    try {
        const response = await fetch("http://localhost:8000/auditors/evaluateLM", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify(
                {
                    auditor_address: auditor,
                    batch_id: task.batchId,
                    model_index: task.modelIndex,
                }
            ),
        });

        const result = await response.json();
        console.log(result);

        fetchAuditorEvaluationBatches();
    } catch (err) {
      console.error("Error evaluating task:", err);
    }
  }

  if (!assignedModels || assignedModels.length === 0) {
    return (
      <div style={{
        border: "1px solid #ddd",
        borderRadius: "8px",
        padding: "1rem",
        marginBottom: "1rem",
        backgroundColor: "#f9f9f9"
      }}>
        <h3 style={{ margin: 0 }}>Auditor: {auditor.slice(0, 6)}...{auditor.slice(-4)}</h3>
        <p style={{ color: "#666", marginTop: "0.5rem" }}>❌ No models assigned.</p>
      </div>
    );
  }

  return (
    <div style={{
      border: "1px solid #ddd",
      borderRadius: "8px",
      padding: "1rem",
      marginBottom: "1rem",
      backgroundColor: "#f9f9f9"
    }}>
      <h3 style={{ margin: 0, fontSize: "1.25rem", fontWeight: "bold" }}>
        Auditor: {auditor.slice(0, 6)}...{auditor.slice(-4)}
      </h3>

      <div className="space-y-3" style={{ marginTop: "1rem" }}>
        {assignedModels.map((task) => (
          <div key={task.modelIndex} style={{
            border: "1px solid #eee",
            borderRadius: "6px",
            padding: "0.75rem",
            backgroundColor: "#fff"
          }}>
            <h4 className="font-bold">🧠 Model #{task.modelIndex}</h4>
            <p><strong>Client:</strong> {task.model?.client?.slice(0, 6)}...{task.model?.client?.slice(-4)}</p>
            <p><strong>CID:</strong> <code style={{
              backgroundColor: "#eee",
              padding: "2px 6px",
              borderRadius: "4px",
              fontSize: "0.9em"
            }}>{task.model?.modelCID || "N/A"}</code></p>
            <p><strong>Audit Batch ID:</strong> {task.batchId}</p>

            {/* Evaluate Button */}
            {!task.hasVoted ? (
              <button
              onClick={() => handleEvaluate(task, auditor)}
              style={{
                padding: "6px 12px",
                backgroundColor: "#10b981",
                color: "white",
                border: "none",
                borderRadius: "6px",
                fontWeight: "bold",
                fontSize: "0.9rem",
                marginTop: "0.5rem",
                cursor: "pointer"
              }}
              className="hover:bg-green-700 transition"
            >
              ✍️ Evaluate
            </button>
            ) : (
            <>
              <p style={{
                color: "green",
                fontWeight: "bold",
                marginTop: "0.5rem"
              }}>
                ✔️ Evaluated
              </p>
              <p><strong>Given Scores:</strong> {task.hasAuditScores}</p>
              <p><strong>Eligible Vote:</strong> {task.isEligible? "✔️ Yes" : "❌ No"}</p>
            </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}