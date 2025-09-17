import React from 'react'

export default function ModelList({lm_submissions}) {

    return (
        
    <div>
      <h2 className="text-2xl font-bold mb-4">🧠 Client Submitted Models</h2>
      <p className="text-gray-600 mb-4">Waiting for auditor assignment...</p>
      {lm_submissions.length === 0 ? (
        <p>No models submitted yet.</p>
      ) : (
        <ul className="space-y-3">
          {lm_submissions.map((sub) => (

            
            <div key={sub.index} className="client-model-card"
            style={{
                marginTop: "1.5rem",
                marginBottom: "1.5rem",
                padding: "1rem",
                border: "1px solid #ccc",
                borderRadius: "8px",
                maxWidth: "600px",
                marginInline: "auto",
                boxShadow: "0 2px 6px rgba(0,0,0,0.1)"
              }}
            >
              <h3 className="font-bold">Model #{sub.index}</h3>
              <p><strong>Client:</strong> {sub.client.slice(0, 6)}...{sub.client.slice(-4)}</p>
              <p><strong>CID:</strong> <code className="bg-gray-100 px-1 rounded">{sub.modelCID}</code></p>
              {!sub.evaluated ? (
                <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
                    <h4 style={{ textAlign: "center", margin: 0 }}> ⏳ Waiting for evaluation</h4>
                </div>
                ) : (
                <>
                <h4 style={{ textAlign: "center", margin: 0, color: sub.approved ? "green" : "red" }}>
                    {sub.approved ? "✅ Approved" : "❌ Rejected"}
                </h4>
                <h4 style={{ textAlign: "center", margin: 0, color: sub.eligible ? "green" : "red" }}>
                    {sub.eligible ? "✅ Eligible" : "❌ Not Eligible"}
                </h4>
                <h4 style={{ textAlign: "center", margin: 0}}>
                    {sub.finalAvgScore}
                </h4>
                </>
                )}
            </div>



          ))}
        </ul>
      )}
    </div>  
    );
}