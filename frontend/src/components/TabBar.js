export default function TabBar({ activeTab, setActiveTab }) {

  const tabs = ["DINDAO", "ModelOwner", "Validators", "Clients" ];
  return (
    <div className="tab-bar">
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => setActiveTab(tab)}
          className={activeTab === tab ? "tab-button active" : "tab-button"}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}