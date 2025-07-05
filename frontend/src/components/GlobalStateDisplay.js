export default function GlobalStateDisplay({ loading, error, GI, GIstatedes }) {
    if (loading) return <div>Loading global state...</div>;
    if (error) return <div className="error">Error: {error.message}</div>;
  
    return (
      <div className="margin-block">
        <h3>Global Iteration: {GI}</h3>
        <h3>Global Iteration State: {GIstatedes}</h3>
      </div>
    );
  }
  