export default function GlobalActions({ onReset, onDistribute, isResetting, isDistributing }) {
    return (
      <div className="margin-block">
        <button
          className="button button--danger margin-block-lr"
          onClick={onReset}
          disabled={isResetting}
        >
          {isResetting ? "Resetting..." : "Reset All"}
        </button>
        <button
          className="button button--primary margin-block-lr"
          onClick={onDistribute}
          disabled={isDistributing}
        >
          {isDistributing ? "Distributing..." : "Distribute Dataset"}
        </button>
      </div>
    );
  }
  