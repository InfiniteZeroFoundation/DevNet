import React, { useState, useEffect, useContext } from "react";
import { TooltipContext } from "../context/TooltipContext";


/** ======================= Global Analytics TAB ======================= */

export default function GlobalAnalyticsTab({GIstate, GI, GIstatestr}) {

    const [loading, setLoading] = useState(true);
    const { showTooltip } = useContext(TooltipContext);
    const [GIaccuracy, setGIaccuracy] = useState([]);



    const fetchGlobalAnalyticsState = async () => {
        try {
            setLoading(true);
            const response = await fetch("http://localhost:8000/globalanalytics/getGlobalAnalyticsState", {
                method: "POST",
            });
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            console.log(data);
            setGIaccuracy(data.GIaccuracy);
            setLoading(false);
        } catch (error) {
            showTooltip(error.message, true);
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchGlobalAnalyticsState();
    }, [GI]);

    return (
        <div className="tab-content">
            <h2>Global Analytics</h2>
            {loading ? (
                <div>Loading...</div>
            ) : GI === 0 && GIstate < 4 ? (
                <div style={{ display: 'flex', alignItems: 'center', color: '#f59e0b', gap: '8px' }}>
                    ⚠️ <strong>Genesis Model Not Created Yet</strong>
                </div>
            ) : GIstate >= 4 ? (
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '16px' }}>
                    <thead>
                        <tr>
                            <th style={{ border: '1px solid #ddd', padding: '8px', textAlign: 'left' }}>GI Number</th>
                            <th style={{ border: '1px solid #ddd', padding: '8px', textAlign: 'left' }}>Pass Score</th>
                            <th style={{ border: '1px solid #ddd', padding: '8px', textAlign: 'left' }}>Accuracy</th>
                        </tr>
                    </thead>
                    <tbody>
                        {GIaccuracy.map((accuracy, index) => (
                            <tr key={index}>
                                <td style={{ border: '1px solid #ddd', padding: '8px' }}>{index}</td>
                                <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                                    {index === 0 ? "N/A" : `${(GIaccuracy[index - 1] - 5)}%`}
                                </td>
                                <td style={{ border: '1px solid #ddd', padding: '8px' }}>{accuracy}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            ) : (
                <div>No data available yet.</div>
            )}
        </div>
    );

}