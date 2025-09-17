import React from 'react';



export default function AuditBatchMO({ AuditBatches }) {
    // Helper to shorten address
    const shorten = (addr) => `${addr.slice(0, 6)}...${addr.slice(-4)}`;
  
    return (
      <div className="p-6 max-w-4xl mx-auto bg-gray-50 font-sans">
        <h1 className="text-3xl font-bold text-center mb-2 text-indigo-800">
          📋 Auditor Batches
        </h1>
        <p className="text-center text-gray-600 mb-8">
          📋 {AuditBatches.length} batches assigned
        </p>
  
        <div className="space-y-6">
          {AuditBatches.map((batch) => (
            <div
              key={batch.batch_id}
              className="client-model-card"
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
              {/* Batch Header */}
              <div className="flex flex-wrap items-center gap-4 mb-4">
                <h2 className="text-2xl font-bold text-gray-800">
                  🧩 Batch #{batch.batch_id}
                </h2>
                <span className="px-3 py-1 bg-indigo-100 text-indigo-800 rounded-full text-sm font-medium">
                  {batch.auditors.length} 👥, {batch.model_indexes.length} 🧠
                </span>
              </div>
  
              {/* Auditors */}
              <div className="mb-4">
                <h3 className="font-semibold text-gray-700 mb-2">
                  👥 Auditors ({batch.auditors.length})
                </h3>
                <ul className="space-y-1">
                  {batch.auditors.map((addr, idx) => (
                    <li key={idx} className="text-sm text-blue-600 font-mono">
                      {shorten(addr)}
                      <span className="text-gray-500 ml-2">({addr})</span>
                    </li>
                  ))}
                </ul>
              </div>
  
              {/* Models */}
              <div className="mb-4">
                <h3 className="font-semibold text-gray-700 mb-2">
                  🧠 Model Indexes ({batch.model_indexes.length})
                </h3>
                <div className="flex flex-wrap gap-2">
                  {batch.model_indexes.map((idx) => (
                    <span
                      key={idx}
                      className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-mono"
                    >
                      #{idx}
                    </span>
                  ))}
                </div>
              </div>
  
              {/* Test CID */}
              <div>
                <h3 className="font-semibold text-gray-700 mb-2">🧪 Test Data CID</h3>
                {batch.test_cid ? (
                  <div className="flex items-center gap-2">
                    <span className="text-green-600">✅</span>
                    <code
                      className="text-xs bg-gray-100 border border-gray-300 px-2 py-1 rounded break-all"
                      title={batch.test_cid}
                    >
                      {batch.test_cid}
                    </code>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-red-600">
                    <span>🚨</span>
                    <span className="italic">No test data provided</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

